"""
src/incident/package.py — export and independently verify a consent
incident (HOD-705, HOD-706).

The exported package is self-contained: manifest, assertions,
observations, and the verification key (with its authority class stated —
an ephemeral demo key says so). verify_package() needs NOTHING from Hodi:
it recomputes every hash, checks the signature with only the public key,
checks every assertion against the assertion-authority matrix, and
RE-RUNS the arbiter's deterministic policy over the packaged assertions,
requiring the reproduced decision to equal the recorded one. The record
proves itself or it fails.
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from src.agents.consent_arbiter import adjudicate_assertions
from src.schema.assertion import TypedAssertion, IncidentDecision
from src.schema.assertion_authority import may_assert
from src.schema.incident import (
    ConsentIncidentManifest, ObservationRecord, assertions_digest, observation_hash,
)
from src.schema.signing import (
    EphemeralEd25519Signer, get_active_signer, is_signature_envelope,
    signable_bytes, verify_envelope,
)


class VerificationReport:
    def __init__(self):
        self.checks: List[Tuple[bool, str]] = []
        self.conclusions: Dict[str, str] = {}

    def add(self, ok: bool, label: str) -> None:
        self.checks.append((ok, label))

    @property
    def all_ok(self) -> bool:
        return all(ok for ok, _ in self.checks)


def export_package(result, public_key_pem: Optional[str] = None,
                   key_authority: Optional[str] = None) -> Dict[str, Any]:
    """Builds the self-contained package from an IncidentResult. The key's
    authority class travels WITH the key: an ephemeral key is labelled, so a
    package signed in a demo cannot pass itself off as production provenance."""
    signer = get_active_signer()
    if public_key_pem is None and signer is not None:
        if isinstance(signer, EphemeralEd25519Signer):
            public_key_pem = signer.public_key_pem
            key_authority = key_authority or (
                "ephemeral — generated for this process, proves mechanism only; "
                "trust it no further than the run that printed it")
        else:
            public_key_pem = signer.public_key_pem()
            key_authority = key_authority or "cloud-kms — verify out of band against /verification-key"
    return {
        "incident_id": result.manifest.incident_id,
        "manifest": result.manifest.model_dump(mode="json"),
        "manifest_hash": hashlib.sha256(
            signable_bytes(result.manifest.model_dump(mode="json"))).hexdigest(),
        "assertions": [a.model_dump(mode="json") for a in result.assertions],
        "observations": [o.model_dump(mode="json") for o in result.observations],
        "verification_key_pem": public_key_pem,
        "verification_key_authority": key_authority or "none — unsigned package",
    }


def verify_package(package: Dict[str, Any]) -> VerificationReport:
    report = VerificationReport()

    # 0. The package parses into the typed models — a package that needs
    # looser parsing than the system that wrote it is already suspect.
    try:
        manifest = ConsentIncidentManifest(**package["manifest"])
        assertions = [TypedAssertion(**a) for a in package["assertions"]]
        observations = [ObservationRecord(**o) for o in package["observations"]]
    except (ValidationError, KeyError) as e:
        report.add(False, f"package parses into typed models ({type(e).__name__}: {str(e)[:80]})")
        return report
    report.add(True, "package parses into typed models")

    # 1. Manifest signature, using only the packaged (or overridden) key.
    key_pem = package.get("verification_key_pem")
    manifest_doc = package["manifest"]
    if not key_pem:
        report.add(False, "manifest signature valid (no verification key in package)")
    elif not is_signature_envelope(manifest_doc.get("signature", "")):
        report.add(False, "manifest signature valid (signature is not an envelope — "
                          "placeholder or absent)")
    else:
        ok = verify_envelope(manifest_doc["signature"], signable_bytes(manifest_doc), key_pem)
        report.add(ok, f"manifest signature valid ({manifest_doc['signature'].split(':', 1)[0]}"
                       f"; key authority: {package.get('verification_key_authority', 'unstated')})")

    # 2. The manifest hash the package advertises is the manifest's real hash.
    recomputed_manifest_hash = hashlib.sha256(signable_bytes(manifest_doc)).hexdigest()
    report.add(recomputed_manifest_hash == package.get("manifest_hash"),
               "manifest hash matches package")

    # 3. Every observation's hash matches the manifest's evidence_hashes.
    for obs in observations:
        recorded = manifest.evidence_hashes.get(obs.observation_id)
        report.add(observation_hash(obs) == recorded,
                   f"evidence hash valid for observation {obs.observation_id}")
    missing = set(manifest.evidence_hashes) - {o.observation_id for o in observations}
    report.add(not missing,
               "every hashed observation is present in the package"
               + (f" (missing: {sorted(missing)})" if missing else ""))

    # 4. The assertion list is the one the manifest bound.
    report.add(assertions_digest(assertions) == manifest.assertions_hash,
               "assertions hash matches manifest")

    # 5. Every assertion is within its role's epistemic authority.
    for a in assertions:
        report.add(may_assert(a.asserted_by_role, a.assertion_class),
                   f"assertion authority respected: {a.asserted_by_role} → {a.assertion_class}")

    # 6. DECISION REPRODUCED: the same deterministic policy over the same
    # assertions must yield the same conclusions. This is the check that
    # makes the record self-proving rather than self-asserting.
    reproduced = adjudicate_assertions(
        assertions, manifest.incident_id,
        decision_id=manifest.decision.decision_id,
        decided_at=manifest.decision.decided_at)
    report.add(reproduced.model_dump(mode="json") == manifest.decision.model_dump(mode="json"),
               f"decision reproducible under {manifest.policy_version}")

    # 7. The structural boundary is present (the schema enforces it; the
    # checklist states it out loud, because that is the product).
    training = manifest.decision.not_determinable.get("MODEL_TRAINING_OCCURRED", "")
    report.add(training.startswith("NOT_ESTABLISHED"),
               "training-membership boundary intact: MODEL_TRAINING_OCCURRED is NOT_ESTABLISHED")

    # 8. Chain link recorded (continuity to the PRIOR manifest is checkable
    # against the incidents log; a lone package can only show the link).
    report.add(bool(manifest.previous_event_hash),
               f"event-chain link recorded (previous: {manifest.previous_event_hash[:16]}…)"
               if manifest.previous_event_hash else "event-chain link recorded")

    for f in manifest.decision.findings:
        report.conclusions[f.claim] = f.status
    report.conclusions["MODEL_TRAINING_OCCURRED"] = "NOT_ESTABLISHED"
    return report
