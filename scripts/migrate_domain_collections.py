#!/usr/bin/env python3
"""
scripts/migrate_domain_collections.py — move domain data into the per-domain
databases so the IAM boundary applies to real rows (HOD-733).

WHY A MOVE AND NOT A COPY. The per-domain databases were created and
IAM-conditioned on 2026-08-14 and left empty; every live collection stayed in
`(default)`. A copy that leaves the originals behind does not tighten anything:
any identity holding the grant-log grant on `(default)` can still read `works`
and `crawler_access` there. Dual presence would let the docs claim a boundary
the data does not have — the exact failure this project exists to avoid. So this
COPIES, VERIFIES, DELETES, and VERIFIES AGAIN.

ON DELETING FROM AN APPEND-ONLY PROJECT. Hodi's runtime identities are
deliberately create-only: no agent service account holds
`datastore.entities.delete`. That property is load-bearing and is NOT relaxed
here. This script runs under an OPERATOR credential, once, out of band — it is
not reachable by any agent, any route, or any deployed workload. It refuses to
touch the grant log or anything else the policy marks as shared, and it appends
a `domain_migrations` record to `(default)` naming exactly what moved, how many
documents, and the digest that proved the copy faithful. The rows move; the
record that they moved does not.

WHAT IT WILL NOT MOVE. `grants`, `revocation_notices`, `revocation_outbox`,
`leases`, `agent_registry_events` and `counterparty_credentials` stay in
`(default)` — that set is read from `DEFAULT_DATABASE_COLLECTIONS` in
src/schema/iam_policy.py rather than retyped, so this script and the gateway
cannot disagree about where a collection belongs.

Usage:
    python3 scripts/migrate_domain_collections.py               # dry run
    python3 scripts/migrate_domain_collections.py --execute
    python3 scripts/migrate_domain_collections.py --verify      # report only
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gateway.gateway import _build_firestore_client  # noqa: E402
from src.schema.iam_policy import (  # noqa: E402
    AGENT_SA_MAP, DEFAULT_DATABASE_COLLECTIONS, database_for_collection,
)

PROJECT = "hodi-2026"

# The collections that actually hold domain data today, with the role that owns
# them. The destination is DERIVED from the policy, never written here.
OWNED_BY = {
    "works": "rights_custodian",
    "crawler_access": "evidence_agent",
    "accrual_audits": "evidence_agent",
    # Authentication material, moving to its own database so the append-only
    # role every agent holds on `(default)` — which includes entities.get and
    # .list — stops granting them every principal's HMAC secret (HOD-745). The
    # owning role is nominal here: database_for_collection() routes credential
    # collections by name, not by role.
    "counterparty_credentials": "rights_custodian",
}


def client(database: str):
    """
    The SAME builder the gateway uses, so this script cannot reach a database
    the running system cannot — including its ADC-then-gcloud-token fallback,
    which is what lets an operator run this from a shell without ADC.
    """
    db = _build_firestore_client(PROJECT, database)
    if db is None:
        raise SystemExit("HODI_OFFLINE=1 is set; this script moves live data and must not "
                         "run against an offline stub.")
    return db


def digest(docs: dict) -> str:
    """Order-independent digest of {doc_id: data}, so a faithful copy is provable."""
    h = hashlib.sha256()
    for doc_id in sorted(docs):
        h.update(doc_id.encode())
        h.update(json.dumps(docs[doc_id], sort_keys=True, default=str).encode())
    return h.hexdigest()


def read_all(db, collection: str) -> dict:
    return {d.id: d.to_dict() for d in db.collection(collection).stream()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="actually move (default: dry run)")
    ap.add_argument("--verify", action="store_true", help="report where the data is and exit")
    ap.add_argument("--backup-dir", default=None,
                    help="where to write the pre-migration JSON backup (required with --execute)")
    args = ap.parse_args()

    default_db = client("(default)")
    plan = []
    for collection, role in OWNED_BY.items():
        dest = database_for_collection(role, collection)
        if collection in DEFAULT_DATABASE_COLLECTIONS or dest == "(default)":
            print(f"  SKIP  {collection}: policy keeps it in (default)")
            continue
        src_docs = read_all(default_db, collection)
        dst_docs = read_all(client(dest), collection)
        plan.append((collection, role, dest, src_docs, dst_docs))
        print(f"  {collection:22} {role:18} (default)[{len(src_docs):>5}] -> "
              f"{dest}[{len(dst_docs):>5}]")

    if args.verify:
        stranded = [c for c, _r, _d, s, _x in plan if s]
        print("\nAll domain data is in its domain database."
              if not stranded else
              f"\nSTILL IN (default): {stranded} — the IAM condition does not apply to these rows.")
        return 1 if stranded else 0

    if not args.execute:
        print("\nDry run. Re-run with --execute --backup-dir <dir> to move.")
        return 0

    if not args.backup_dir:
        print("--execute requires --backup-dir: nothing is deleted before it is written down.",
              file=sys.stderr)
        return 2
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    for collection, role, dest, src_docs, dst_docs in plan:
        if not src_docs:
            print(f"\n{collection}: nothing left in (default) — already migrated.")
            continue

        print(f"\n{collection}: {len(src_docs)} documents  (default) -> {dest}")
        before = digest(src_docs)

        # 1. Back up BEFORE anything is written or removed.
        (backup_dir / f"{collection}.json").write_text(
            json.dumps({"collection": collection, "source": "(default)", "digest": before,
                        "documents": src_docs}, indent=2, default=str))
        print(f"  backup written ({before[:16]}…)")

        # 2. Copy with .create() — the destination inherits append-only
        #    semantics, and a colliding id fails loudly instead of overwriting.
        dest_db = client(dest)
        written = 0
        for doc_id, data in src_docs.items():
            if doc_id in dst_docs:
                continue
            dest_db.collection(collection).document(doc_id).create(data)
            written += 1
        print(f"  copied {written}")

        # 3. Verify the copy is FAITHFUL before removing the original.
        #
        # CONTAINMENT, not equality. The first version compared the whole
        # destination's digest against the source's, which only holds when the
        # destination started empty — so the incremental sweep of records
        # written during the cutover window aborted, correctly refusing to
        # delete what it could not prove it had copied. What must be true is
        # that every source document is present in the destination byte for
        # byte; the destination legitimately holds more.
        copied = read_all(dest_db, collection)
        missing = [k for k in src_docs if k not in copied]
        differing = [k for k in src_docs
                     if k in copied and digest({k: copied[k]}) != digest({k: src_docs[k]})]
        if missing or differing:
            print(f"  ABORT: {len(missing)} missing and {len(differing)} differing in "
                  f"{dest} — nothing deleted.", file=sys.stderr)
            return 1
        print(f"  verified: all {len(src_docs)} source documents present in {dest}, byte for byte")

        # 4. Only now remove the originals, in batches.
        batch, n = default_db.batch(), 0
        for doc_id in src_docs:
            batch.delete(default_db.collection(collection).document(doc_id))
            n += 1
            if n % 400 == 0:
                batch.commit(); batch = default_db.batch()
        batch.commit()
        remaining = read_all(default_db, collection)
        if remaining:
            print(f"  WARNING: {len(remaining)} documents remain in (default)", file=sys.stderr)
        else:
            print(f"  removed from (default)")

        # 5. Record the move itself, durably, in the database it left.
        default_db.collection("domain_migrations").document(
            f"{collection}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}").create({
                "collection": collection,
                "owning_role": role,
                "owning_service_account": AGENT_SA_MAP[role]["sa_email"],
                "source_database": "(default)",
                "destination_database": dest,
                "document_count": len(src_docs),
                "content_digest_sha256": before,
                "migrated_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": ("Moved so the per-domain IAM condition applies to these rows. The rows "
                         "left (default); this record of their leaving did not. Performed once, "
                         "out of band, under an operator credential — no agent identity holds "
                         "datastore.entities.delete and none was used."),
            })
        print(f"  migration recorded in (default)/domain_migrations")

    print("\nDone. Re-run with --verify to confirm nothing is stranded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
