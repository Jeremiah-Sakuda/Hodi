# Hodi — recording script

> **CURRENT AS OF 2026-08-25, revision `hodi-evidence-endpoint-00059-z55`.** Every command in this
> file was executed against a deployed revision and every duration below is the round-trip that run
> produced — but they were **not all produced on the same day**, and the table says which. The hero
> cascade and the live boundary test were re-measured on **2026-08-25 against `00059-z55`**, after
> `/api/v1/revoke` was cut over to the private revocation worker; the natural-language licence and the
> signature verification are from **2026-08-14 against `00054-swn`**, on code paths the cutover did not
> touch. Where a figure carries a date, that date is the one to believe. `docs/metrics.json` is the
> source; `make metrics` regenerates it.
>
> **Re-measure the cascade before you record.** The deployed revision is now `00061-jwh`; the
> cascade figures below were measured on `00059-z55`, before the HOD-746 selection change. That
> change swaps one comparison for another and should not move the clock, but nobody has timed it
> since — and timing it needs the artist credential, which lives with you and not in the repo or
> CI. Do not narrate a number nobody has observed on the revision you are filming. The earlier stale-banner warning is retired because the thing it
> warned about was fixed rather than restated — see the two paragraphs immediately below, which record
> what was wrong, because the same defect will recur if only the symptom is remembered.
>
> **Two commands in this script would have failed on camera, and did.** Run exactly as previously
> written, Beat 3 and the hero's Frames A and C returned **HTTP 422 — `work_id` Field required**:
> `ScopeRequest.work_id` and `NaturalScopeRequest.work_id` are required with no default
> ([src/api/buyer_api.py:191](../src/api/buyer_api.py#L191), [:288](../src/api/buyer_api.py#L288)), and
> the bodies here carried none. A banner had warned about this since the build that introduced it; the
> banner was written and the bodies were never changed. **A warning is not a fix.**
>
> **And a third failure the banner did not predict.** With `work_id` added, the hero's Frame A still
> returned `permitted: false` — its scope hardcoded `valid_from: 2026-08-09`, while
> `make recording-prep` seeds the grant with `valid_from = now`. A request window that opens before
> the grant's is not contained in it, so it is correctly denied. Frame A is the frame that must show
> the licence **granted**; a false there is not a slow take, it is no hero beat at all. Both bodies
> below now compute `valid_from` at call time. `tests/test_recording_script_contract.py` parses this
> file and fails the build if any request body here omits a required field of the route it posts to.

**Target 3:30 · hard cap 4:00 · 30 seconds of insurance**
Everything except the recording. All durations below were **measured** — the source for each is named,
and the whole sequence was re-run end to end on **2026-08-14** against revision `00054-swn`. The
boundary denial returns **6/6 HTTP 403 including Part C**; the hero cascade appends under create-only
IAM with the affected set, derived scopes and issued notices all correct; a non-owner revoke is
refused 403. Warm cascade **2389 ms median**. Re-measure with `make metrics` if you record more than a
day from now.

> **The signature narration changed, and it changed in your favour.** Earlier versions of this script
> told you to say the `signature` field reads `UNSIGNED_PLACEHOLDER`. **It no longer does.** The
> deployed service signs notices and receipts with Cloud KMS, and the field now reads
> `KMS-ECDSA-P256-SHA256:hodi-provenance/cryptoKeyVersions/1:…`. Saying "unsigned" on camera would
> narrate something the screen contradicts *and* throw away the strongest provable claim in the
> submission. The new closing beat verifies a notice with the public key alone — see Beat 4.

Supersedes PRD §6's shot list. Three things changed since it was written and the budget changes
with them:

| Change | Effect on the shot list |
|---|---|
| The security beat is now the **live boundary denial** (6/6 HTTP 403 including Part C) | Replaces the prompt-inspector-only framing. Stronger and faster. |
| **Natural-language licensing** exists (Gemini 3.5 Flash → typed Scope → lattice) | New beat. It is the "model interprets intent, the lattice decides permission" thesis in one command. |
| The artist console is **read-only** | There is no revoke button to click on camera. The hero runs from the terminal against the deployed API. |

---

## The timing problem, stated up front

**The actions are far faster than the beats.** This is the single thing to internalise before you
record:

| Action | Measured (date and revision named per row) | Beat budget |
|---|---|---|
| Revocation cascade, **1 affected grant** | **2334 – 3307 ms**, median **2389 ms**, mean **2563 ms** over 7 warm runs (2026-08-25, rev `00059-z55`, through the private worker) | 45 s |
| Revocation cascade, **2 affected grants** | **5086 / 5275 / 4953 ms** (2026-08-09) — see the trap below | — |
| `POST /api/v1/license`, **permitted** (Frame A) | **1495 – 2036 ms**, ~1675 ms avg over 6 warm runs (2026-08-14, `00054-swn`) | — |
| `POST /api/v1/license`, **denied** (Frame C) | **1591 ms** — it pays the custodian hop before it can refuse (2026-08-14, `00054-swn`) | — |
| Natural-language license | **3751 / 3885 / 4141 ms**, ~3.9 s avg warm (2026-08-14, `00054-swn`) | 30 s |
| Full boundary test, 6 denials | **8.62 / 8.91 / 9.35 s** warm, avg **8.96 s** (2026-08-25) | 20 s |
| `make demo`, all 7 beats | **1.4 – 1.8 s** (2026-08-09) | — |
| Quarantine drill | 1114 ms server-side; **7.3 s** cold / 1.5 s warm round-trip (2026-08-09) | 20 s |

**Every figure rose, and the reason is the architecture.** The cascade went ~737 → ~1896 → ~2389 ms and the
permitted licence ~712 → ~1675 ms when the four conflict-domain roles became four separately-deployed
Cloud Run workloads. Both paths check that the artist owns the work; that check reads `works`; and
`works` now lives in `hodi-identity` behind the rights-custodian service, so an in-process call became
an authenticated HTTPS hop the front door **cannot bypass** — its identity is refused by Google IAM on
every domain database. About 1.2 seconds is what the boundary costs. If you find yourself wishing for
the old numbers, note what they were the speed of: one process holding credentials for every domain.

So the hero beat is **not** 45 seconds of waiting. It is ~2.4 s of action wrapped in 45 s of
*before* and *after*: the license granted, the command, the cascade output, the same license refused.
Plan the shot as three static frames with one instant transition, not as a progress bar.

### The 5-second trap in the hero beat — read this before the first take

The cascade's cost is **one Gemini notice-drafting call per affected grant that is not in the
committed response cache.** With one affected grant it is ~2.4 s. With two, add roughly 4.7 s of live
model call on top, and it is reproducibly so — not a cold start you can warm away.

`work-repo-001` carries two grants: `grant-acme-il-001` (the demo grant, cached, fast) and
`grant-seed-2` to `buyer-acme-2` (**not** cached — every revocation touching it pays a live model
call). As left on 2026-08-09, `grant-seed-2` is **revoked**, so the affected set is 1 and the beat is
fast. Pre-flight step 5 verifies this; do not skip it.

If you would rather show the cascade reaching two counterparties, that is a legitimate choice and the
story is arguably richer — but budget **~6.5 s** of dead air, do not burn in a wall clock that
contradicts the "one call, instant" framing, and re-grant `grant-seed-2` first (snippet in
*Between takes*). **The recommendation is the one-grant shot.** The thesis of this beat is
containment across the *scope lattice* — all four use types derived from the partial order — and one
affected grant demonstrates that completely.

**Do not speed-ramp or cut mid-command.** The wall clock is the proof. If a command takes 2.4 s, show
that it took 2.4 s. A legal revocation cascading across the lattice in under two seconds — while every
domain read crosses an authenticated service boundary the caller cannot bypass — is a stronger claim
than a faster number produced by one process trusted with everything.

---

## The one command that puts the system in the right state

```bash
make recording-prep
```

Idempotent. Seeds the demo grant, holds `grant-seed-2` revoked, deactivates throwaway credentials,
then **reports what it verified** — both grant statuses from the fold, the affected-set size, whether
each affected grant's notice prompt is in the committed cache, and the resulting predicted cascade
round-trip. It exits non-zero on a state it cannot fix, so a green run is the pre-flight.

**Between every take:**

```bash
make recording-reset
```

Same guarantees, grants only, no network probe. The hero beat revokes something, so after take one
the state is wrong for take two — this is the command that fixes it. Run it even when you think you
do not need to.

Neither command touches the `works` collection, and neither deletes anything: `grant-seed-2` is
revoked by appending a revoking event, exactly as the system does in production.

Steps 1–3 and 6–9 below are the parts a script cannot do for you.

---

## Pre-flight checklist — run once, before the first take

```bash
cd "path/to/Hodi"
```

1. **Repo state is the submitted state.**
   ```bash
   git status --porcelain && git log --oneline -1
   ```
   Expect: no output from the first command.

2. **CI is green** (it goes on screen in Beat 8).
   ```bash
   gh run list --workflow=verify.yml --branch main --limit 1
   ```

3. **Everything offline passes** — if any of these is red, stop and fix before recording.
   ```bash
   make test && make verify-scopes && make compliance && make demo
   ```

4. **Seed the hero grant and hold the affected set at 1.**
   ```bash
   make recording-prep
   ```
   Expect: `RECORDING STATE READY — cascade on the ~2.4 s path.` If it says `~7.1 s`, the affected
   set is 2 — read its report, it names the grant responsible.

5. **Confirm the boundary holds on the deployed service.**
   ```bash
   make demo-live
   ```
   Expect: **6 HTTP 403s** and `ALL LIVE BOUNDARY TESTS PASSED`. It writes nothing, so it does not
   disturb the state step 4 just set. (You do not need to rehearse the cascade to learn the
   affected-set size — step 4 computes it read-only and prints it.)

6. **Warm the service** so Beat 3 doesn't eat a 7 s cold start on camera.
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://hodi-evidence-endpoint-406699565497.us-central1.run.app/
   ```
   Run this again within ~5 minutes of each take. Cloud Run has `min-instances=0`; if it idles, the
   next call pays the cold start.

7. **Have both credentials in the shell.** Beat 3 and the hero's Frames A/C need a *counterparty*
   credential; the hero's Frame B needs an *artist* credential. Neither secret is in the repo.

   Registered and active as of 2026-08-09 (verified against `counterparty_credentials`):

   | Key id | Principal | Counterparty | Used by |
   |---|---|---|---|
   | `key-acme-il` | counterparty | `acme-intelligence-labs` | Beat 3, hero Frames A and C |
   | `key-artist-jeremiah` | artist | `artist-jeremiah` | hero Frame B |

   ```bash
   export HODI_CP_KEY=key-acme-il
   export HODI_CP_SECRET='<the secret printed when you seeded it>'
   export HODI_ARTIST_KEY=key-artist-jeremiah
   export HODI_ARTIST_SECRET='<the secret printed when you seeded it>'
   ```

   **Do not let these scroll on screen.** Set them in a shell you never point the camera at, or set
   them before you start recording and clear the terminal.

   **If you no longer have a secret,** re-seed the key — this *rotates* it, so the old secret stops
   working, which is the intended behaviour:
   ```bash
   python3 scripts/seed_counterparty_credential.py acme-intelligence-labs key-acme-il counterparty
   ```
   ```bash
   python3 scripts/seed_counterparty_credential.py artist-jeremiah key-artist-jeremiah artist
   ```
   The secret prints once. Capture it before you clear the screen.

   > `key-artist-verify-0809` and `key-cp-verify-0809` also exist and are **deactivated**
   > (`active: false`). They were created on 2026-08-09 solely to re-verify the live beats for this
   > script and were disabled rather than deleted, because credential state is auditable history.
   > Do not use them; they will 403.

8. **Browser tabs open, in this order, logged out or in a clean profile:**
   1. `https://github.com/Jeremiah-Sakuda/Hodi` — README, badge visible
   2. `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/works`
   3. `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json`
   4. `docs/architecture/diagram_b_what_hodi_will_not_say.png` (open the file, full screen)
   5. Cloud Run → `hodi-evidence-endpoint` → **Revisions**
   6. Cloud Scheduler → both jobs, **Last run** column visible
   7. `https://jeremiah-sakuda.github.io/Hodi/blog/seven-ways-to-lie-to-yourself-in-code.html`

9. **Terminal setup.** One terminal, large font, plain prompt, wide enough that no output wraps.
   `make demo` output is 80 columns — size for that.

---

## Between takes — reset

The only beat that mutates state is the hero. Reset it with:

```bash
make recording-reset
```

It is idempotent, restores the grant to active, re-revokes `grant-seed-2` if anything re-granted it,
and re-prints the affected-set size and predicted timing so you are never guessing which path the
next take is on. Nothing
else needs resetting: `make demo` is offline and stateless, `make demo-live` writes nothing, and the
drill is structurally write-free.

**Never** point the hero at a work id you care about. `work-repo-001` is the seeded demo target.

**If you want the two-counterparty cascade instead** (and the ~5.4 s it costs), re-grant
`grant-seed-2` before each take. There is no seeder script for it — `scripts/seed_firestore.py`
would also rewrite the works collection and drop the proof URIs `make verify-manifest` checks, so use
this targeted re-grant, which is the documented re-grant mechanism (a new `granted` event that
supersedes):

```bash
python3 -c "
import os,sys,uuid,subprocess
from datetime import datetime, timezone
sys.path.append(os.getcwd())
from google.cloud import firestore
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope
try: db = firestore.Client(project='hodi-2026')
except Exception:
    tok = subprocess.check_output(['gcloud','auth','print-access-token']).decode().strip()
    from google.oauth2 import credentials as c
    db = firestore.Client(project='hodi-2026', credentials=c.Credentials(tok))
t = datetime.now(timezone.utc)
e = GrantEvent(event_id=str(uuid.uuid4()), grant_id='grant-seed-2', work_id='work-repo-001',
    counterparty_id='buyer-acme-2', kind='granted', issued_at=t, signature='sig-seed-2',
    scope=Scope(use_type='training', model_class='all_models', derivative_retention=True,
                attribution_required=True, commercial=True, valid_from=t, valid_until=None))
db.collection('grants').document(e.event_id).set(e.model_dump())
print('re-granted grant-seed-2 as', e.event_id)"
```

---

## The beats

### Beat 1 — Cold open: the registered work · 15 s

**On screen:** browser tab 2 (`/works`), scrolled to `work-repo-001`.
**Burn in the thesis lower-third at 0:08** — *"Your voice is in a product you never agreed to."*

**Say:** the corpus is my own published work. Every registration carries a control tier, and the
tier is never hidden — **as of 2026-08-25 no work is `verified_control`**; all five are
`asserted`, and the API says so rather than rounding up.

> Accuracy note: do **not** say "five verified works", and do **not** say "one verified work" —
> that was true of the script until 2026-08-25 and was never true of the system. The repository work
> claimed `verified_control` on a signed-commit proof; the repository has never had a signed commit,
> and the function issuing the proof checked only that its arguments were non-empty. It refuses now.
> Saying the tier is never hidden is a stronger beat when the honest number is zero.

---

### Beat 2 — The four conflict walls, and the cloud they run on · 30 s

**Command:**
```bash
make demo
```
**Measured: 1.4–1.8 s for all seven beats.** Let it run to completion, then scroll back to Beat 5.

**On screen:** the Beat 5 block — four `[DENIED]` lines, each with a structured
`PolicyDenialEvent` above it.

**Say:** four agents, four service accounts, separated by conflict of interest rather than task. A
monolith here would itself be the violation. Every denial is a structured event, never a silent
refusal.

> Say **"workload identities"** — identity, commercial, evidence, and adjudication are four private
> Cloud Run services under distinct service accounts and named databases. The front door cannot read
> those databases and must invoke the owning workload. The shared append-only grant log remains in
> `(default)`, where counterparty row separation is gateway-enforced. Do not describe the fleet as one
> process. Cascade timings were re-measured 2026-08-25 (median 2389 ms warm) and every figure in this
> file is that run's. The revocation-route cutover to the private worker is **deployed and verified**
> as of 2026-08-25 — `/api/v1/revoke` executes through the private worker, and the hero beat's
> figures below are that path's.

**Frame B — the cloud, ~10 s.** Two browser tabs, ~5 s each:
1. Cloud Run → the five services, then Revisions → the serving revision
2. Cloud Scheduler → both jobs `ENABLED` with real **Last run** timestamps

**Say:** *(≈24 words)*
"Five Cloud Run services, scale-to-zero, one per conflict domain. Two scheduled jobs with real
execution history — the nightly teardown fires on its own cron, unattended."

> **This beat was Beat 8 and is now Beat 2, deliberately.** At the end of the reel the Google Cloud
> proof was the first thing an overrun ate, and a cloud-infrastructure category cannot afford for its
> cloud evidence to be the optional part. At 0:35 it is load-bearing and unskippable: the walls are
> claimed in Frame A and shown to be real infrastructure in Frame B, before anything is asked of them.

---

### Beat 3 — The model interprets intent, the lattice decides · 30 s *(was 35)*

**Command** (paste as one block; it prints its own wall clock):
```bash
python3 - <<'EOF'
import json, hmac, hashlib, os, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = os.environ["HODI_CP_KEY"], os.environ["HODI_CP_SECRET"]
body = {"work_id": "work-repo-001",   # REQUIRED — omitting it is a 422 before timing starts
        "request_text": "We would like to fine-tune an open-weights model on this work "
                        "for non-commercial research, US and Canada only, with attribution."}
raw = json.dumps(body).encode(); ts = datetime.now(timezone.utc).isoformat()
sig = hmac.new(SECRET.encode(), f"{KEY}\n{ts}\n{hashlib.sha256(raw).hexdigest()}".encode(), hashlib.sha256).hexdigest()
req = urllib.request.Request(BASE + "/api/v1/license/natural", data=raw, headers={
    "Content-Type": "application/json", "X-Hodi-Key-Id": KEY,
    "X-Hodi-Timestamp": ts, "X-Hodi-Signature": sig})
t0 = time.perf_counter()
r = json.loads(urllib.request.urlopen(req, timeout=120).read())
print(f"{(time.perf_counter()-t0)*1000:.0f} ms")
print(json.dumps(r, indent=2))
EOF
```

**Measured: 3751 / 3885 / 4141 ms**, ~3.9 s warm (2026-08-14, rev `00054-swn`), `permitted = true`.
One server-side Gemini call. **Burn in the wall clock.**

**On screen:** the plain-English request, then the returned `interpreted_scope` — verified on
2026-08-14 to come back as `fine_tuning` / `open_weights` / `commercial: false` /
`attribution_required: true` / `territory: ["US","CA"]`, with `valid_from` stamped at request time —
plus `interpreter_model: gemini-3.5-flash` and the receipt.

**Say:** the buyer asks in English. Gemini 3.5 Flash structures it into a typed scope — and that is
*all* it does. The lattice decides permission, deterministically. An interpretation carrying
anything other than a valid scope is rejected, not coerced. **The model never grants anything.**

---

### Beat 4 — HERO: the revocation cascade · 45 s *(never cut)*

**Frame A (before, ~10 s).** Do **not** dump the raw event log — it is append-only and deep (98 events
for `work-repo-001` as of 2026-08-14, and it grows two per take), and its first line is a
`SIG_REVOKED` event from an earlier take, which is the worst possible opening frame. Show the
*answer* instead: ask for the licence and watch it be granted.

```bash
python3 - <<'EOF'
import json, hmac, hashlib, os, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = os.environ["HODI_CP_KEY"], os.environ["HODI_CP_SECRET"]
# valid_from is stamped AT CALL TIME, not hardcoded. `make recording-prep` opens the grant's
# window at seed time, and permits() requires the REQUEST window to be contained in the GRANT
# window — so a hardcoded past date is correctly denied and there is no hero beat.
SCOPE = {"use_type": "fine_tuning", "model_class": "open_weights", "commercial": False,
         "attribution_required": True, "territory": ["US", "CA"],
         "valid_from": datetime.now(timezone.utc).isoformat()}
raw = json.dumps({"work_id": "work-repo-001",   # REQUIRED — omitting it is a 422
                  "counterparty_id": "acme-intelligence-labs", "requested_scope": SCOPE,
                  "raw_document_b64": "aGVsbG8="}).encode()
ts = datetime.now(timezone.utc).isoformat()
sig = hmac.new(SECRET.encode(), f"{KEY}\n{ts}\n{hashlib.sha256(raw).hexdigest()}".encode(), hashlib.sha256).hexdigest()
req = urllib.request.Request(BASE + "/api/v1/license", data=raw, headers={
    "Content-Type": "application/json", "X-Hodi-Key-Id": KEY,
    "X-Hodi-Timestamp": ts, "X-Hodi-Signature": sig})
t0 = time.perf_counter()
r = json.loads(urllib.request.urlopen(req, timeout=120).read())
print(f"{(time.perf_counter()-t0)*1000:.0f} ms   permitted = {r['permitted']}")
print(json.dumps(r, indent=2))
EOF
```

**Measured: 1495 – 2036 ms, ~1675 ms over 6 warm runs, `permitted = True`**, `licensable_set =
["training", "open_weights"]`, with a receipt whose `signature` is a real
`KMS-ECDSA-P256-SHA256:…` envelope (2026-08-14, rev `00054-swn`). This frame is immune to log
churn — it reads the *fold*, not the event dump, so it looks identical on take one and take five.

**Frame B (the action, ~5 s).** Paste and run:
```bash
python3 - <<'EOF'
import json, hmac, hashlib, os, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = os.environ["HODI_ARTIST_KEY"], os.environ["HODI_ARTIST_SECRET"]
raw = json.dumps({"work_id": "work-repo-001", "revoked_use_type": "training"}).encode()
ts = datetime.now(timezone.utc).isoformat()
sig = hmac.new(SECRET.encode(), f"{KEY}\n{ts}\n{hashlib.sha256(raw).hexdigest()}".encode(), hashlib.sha256).hexdigest()
req = urllib.request.Request(BASE + "/api/v1/revoke", data=raw, headers={
    "Content-Type": "application/json", "X-Hodi-Key-Id": KEY,
    "X-Hodi-Timestamp": ts, "X-Hodi-Signature": sig})
t0 = time.perf_counter()
r = json.loads(urllib.request.urlopen(req, timeout=120).read())
print(f"{(time.perf_counter()-t0)*1000:.0f} ms")
print(json.dumps(r, indent=2))
# Frame D verifies this notice with the public key alone. Save it now.
json.dump(r["issued_notices"][0], open("/tmp/hodi_notice.json", "w"))
EOF
```

**Measured: 2334 – 3307 ms** round-trip warm, median **2389 ms**, mean **2563 ms** over 7 runs (2026-08-25, revision `00059-z55`), with
one affected grant. `metrics.json` records 2263 ms cold / 737 ms warm. It rose from ~519 ms when the
cascade gained an execution lease and an idempotency outbox — a retry cannot double-issue a notice,
and an abandoned worker cannot commit late. **Burn in the wall clock — the last observed run was
roughly two seconds, not under one, and it is buying the authenticated ownership hop plus exactly-once
effects. Re-measure after the private-worker cutover and narrate only that observed value.**

On screen, in the response (all seven top-level keys confirmed present on 2026-08-14):
- `derived_scopes` — `fine_tuning`, `human_reference`, `rag_retrieval`, `training`, walked from the
  lattice's covering relation, not enumerated in code
- `structured_derivation` — each step with its `parent` and the reason (`training ⊃ fine_tuning`)
- `affected_grants` — the grant, its counterparty, its original scope
- `issued_notices` — each notice carries `revocation_id`, `grant_id`, `counterparty_id`, `revoked_at`
  and `signature`, and that signature reads
  **`KMS-ECDSA-P256-SHA256:hodi-provenance/cryptoKeyVersions/1:MEQCIE4O…`** — a real ECDSA P-256
  signature over the canonical bytes, made by a private key that has never left Cloud KMS
- `operation_id` and `replayed_effects` — the idempotency outbox, visible. `replayed_effects: 0` on a
  first call; run the same revoke twice and the second returns the *same* `operation_id` with the
  effects replayed rather than re-issued. This is the ~220 ms the cascade got slower to buy.

**Frame C (after, ~20 s).** Re-run **the Frame A command, unchanged.** Same request, same
counterparty, same scope.

**Measured: 1591 ms, `permitted = False`**, `licensable_set = []`, `explicit_exclusions =
["fine_tuning", "open_weights"]` (2026-08-14, rev `00054-swn`). The denial is no longer the fast
path: it pays the same rights-custodian hop before it can refuse, which is the correct order —
you cannot decide a request about a work without first establishing the work.

> **Accuracy note (read once).** The demo grant is held at **`training`** (the broadest use),
> so revoking `training` correctly terminates it and the notice withdraws all four downstream
> uses. Do **not** seed it at a narrower use like `fine_tuning`: revoking `training` must NOT
> terminate a narrower grant, and `make recording-prep` seeds `training` for exactly this
> reason. The cascade selecting the wrong grants was the defect fixed on 2026-08-12.

**Say:** *(≈22 words — do not extend this; the flip carries the beat, not the explanation)*
"One call. `fine_tuning` fell with `training` because the lattice says so — nobody coded that rule.
The grant isn't deleted; a new event supersedes it."

> The A→C flip is the whole beat: *the identical request, granted and then refused, about two seconds
> apart.* That is worth more on camera than any amount of JSON, and it cannot be faked by a stub —
> the same endpoint answered both times.

**Frame D (the proof, ~10 s) — paid for out of Frame C, which is generous at 25 s for a
455 ms command. The hero stays at its 45 s budget: A 10 + B 5 + C 20 + D 10.** Take the
notice the cascade just issued and verify it **without Hodi**:

```bash
curl -s https://hodi-evidence-endpoint-406699565497.us-central1.run.app/verification-key | python3 -c "import json,sys; print(json.load(sys.stdin)['public_key_pem'])" > /tmp/hodi_pub.pem
python3 scripts/hodi_verify.py /tmp/hodi_notice.json --key /tmp/hodi_pub.pem
```

**Verified 2026-08-14 against rev `00054-swn`:** `✓ document signature valid
(KMS-ECDSA-P256-SHA256)` → `VERIFIED`, exit 0. Then change one byte and run it again:

```bash
python3 -c "import json; d=json.load(open('/tmp/hodi_notice.json')); d['counterparty_id']='tampered-labs'; json.dump(d,open('/tmp/hodi_notice_bad.json','w'))"
python3 scripts/hodi_verify.py /tmp/hodi_notice_bad.json --key /tmp/hodi_pub.pem
```

**Verified the same day:** `✗ document signature INVALID` → `VERIFICATION FAILED`, exit 1.

**Say:** *(≈25 words)*
"The private key never left Cloud KMS. This used the public key alone — no Hodi service. A court
could verify this notice; Hodi couldn't forge it. One byte, and it fails."

**Reset before the next take:** `make recording-reset`

---

### Beat 5 — Security: the boundary, attacked live · 20 s

```bash
make demo-live
```
**Measured: 8.62 / 8.91 / 9.35 s warm, avg 8.96 s** (2026-08-25, `docs/metrics.json`
→ `live_boundary_proof`). **This script said "~2.2 s warm" until 2026-08-25, and that figure predated
the domain split** — it was measured when one process answered all six probes without leaving
itself. Six denials now cross real service boundaries. It still fits the 20 s
beat, but plan for nine seconds of screen time, not two: do not start narrating over it expecting to
finish.

**On screen:** all three parts, ending on **6 × HTTP 403** and `ALL LIVE BOUNDARY TESTS PASSED`.

**Say:** *(≈40 words)*
"Part B replays the real cross-buyer exploit that worked against this service on August 7th —
unauthenticated, it read another buyer's grant and got a receipt. All six refused now. The exploit is
a permanent regression test, and CI fails if any mutating route forgets to authenticate."

> This is the strongest 20 seconds in the video. A boundary that was broken and rebuilt, with the
> attack preserved, beats a boundary that was never tested.

---

### Beat 6 — Failure tolerance: quarantine and reroute · 20 s

**Command:** `make demo` (already run in Beat 2 — scroll to **Beat 5C**), or run the deployed drill:
```bash
# deployed variant, artist-credentialed, structurally write-free
# (same signing block as Beat 4, POST /api/v1/fleet/delegation_drill, body {"deadline_seconds": 1.0})
```
**Measured: 1114 ms server-side; 7.3 s cold / 1.5 s warm round-trip.** Prefer the `make demo` version
on camera — it is instant and deterministic.

**On screen:** the propagator ABANDONED by the supervisor, then QUARANTINED, deregistered, rerouted,
`COMPLETED_DEGRADED`, `0 notices issued`.

**Say:** *(≈40 words)*
"The worker is forced into an infinite loop. The supervisor writes `TaskAbandoned` itself — the
worker is still looping and has reported nothing. The registry deregisters it, and a standby returns
a stated partial result and writes nothing, because the log is append-only."

---

### Beat 7 — Diagram B: the honesty beat · 15 s *(never cut)*

**On screen:** browser tab 4, `diagram_b_what_hodi_will_not_say.png`, full screen. Hold on the
struck-through fifth column.

**Say:** *"Here is what Hodi will not tell you."* Four typed evidence classes, no score, no total.
And a fifth column that does not exist: training-set membership. Not because we ran out of time —
because it is not determinable, there is no enum value for it, and the schema physically cannot
express the claim. Revocation terminates a grant. It does not un-train a model.

Then the measured finding — **re-measured 2026-08-25; these are the numbers on the screen behind you,
so say these and no others**: 4430 accrued access records. **Sixteen** match a crawler signature —
two distinct crawler user agents, sixteen visits between August 11th and August 25th. Every single
one fetched `/robots.txt`. **Not one** fetched `/.well-known/hodi.json` — one request away, named in
that very `robots.txt`, where the machine-readable terms are served. They asked whether they were
allowed to crawl. Not one asked what they were allowed to *do with the work*.

> **The narration said 3291 records and "nine" while Diagram B filled the screen behind it with 4430
> and 16.** The beat marked "never cut" was the beat that contradicted its own visual. Both halves
> now come from `docs/metrics.json`, and `make check-docs` fails the build if this file drifts from
> it — the same guard the README and the Devpost draft are already held to, extended to the one
> document whose numbers are spoken out loud.
>
> This is the thesis in sixteen records, and it beats both prior versions ("nobody came", then "one
> crawler came"). Do not name the vendors on camera — they did nothing wrong, and the point is not
> who they are. The correction line still lands if you want it: the count read zero for a week
> because the detector's pattern required a word boundary before `bot`, so a vendor prefix glued
> onto `bot` never matched. *"The number was zero until the detector could see."*

> Read those numbers off `docs/metrics.json` on the day you record. `make check-docs` keeps the
> README, the diagram and the submission text in agreement, but the diagram PNG is only as fresh as
> its last render.

---

### Beat 8 — Close · 10 s

**On screen:** the README title card, or the thesis lower-third.
**Say:** *Hodi* is what you call at someone's door before entering. **Hodi is the knock.**

---

## Budget

| # | Beat | Budget |
|---|---|---|
| 1 | Cold open — registered work | 15 s |
| 2 | Four conflict walls **+ Google Cloud proof** | 30 s |
| 3 | Model interprets, lattice decides | 30 s |
| 4 | **HERO — revocation cascade** (A 10 · B 5 · C 20 · D 10) | 45 s |
| 5 | Security — live boundary, 6 denials | 20 s |
| 6 | Quarantine and reroute | 20 s |
| 7 | **Diagram B — the honesty beat** | 15 s |
| 8 | Close | 10 s |
| — | Transitions | 15 s |
| | **Total** | **200 s (3:20)** |

**Ten seconds under the 3:30 target, 40 s under the hard cap.** Narration across all eight beats is
**367 words** — at a deliberate 150 wpm that is 147 s of speech inside 200 s of runtime, so every beat
has air in it. If you find yourself rushing, you are reading something not written below.

**Nothing needs cutting.** But if you overrun on the day, use this order — deepest reserve first, and
do not improvise:

1. **Quarantine → 10 s** (the two transcript lines only, no setup) — **−10 s**
2. **Cold open → 10 s** (one burned-in stat card) — **−5 s**
3. **Conflict walls Frame A → 12 s** (hold Diagram A with narration over it) — **−8 s**

That is 23 s of reserve without touching the hero, the security beat, the Google Cloud proof,
Diagram B, or the thesis. **The Google Cloud proof is no longer in the cut ladder at all** — in a
cloud-infrastructure category it is not reserve, and it now sits at 0:35 where an overrun cannot
reach it.

**Never cut:** the revocation cascade at 45 s · the live boundary denials · the Google Cloud proof ·
Diagram B · the thesis at 0:08 and at close · the burned-in wall clock's continuity.

---

## Things that will bite you

- **Cold start, now on more than one service.** `min-instances=0` everywhere. A cold cascade measured
  **19874 ms** with the front door, the rights-custodian AND the revocation worker all cold, against ~2563 ms warm. The chain is three services deep now.
  Warming the front door alone is nowhere near enough — a cold hero beat is TWENTY SECONDS. Run the
  hero command once as a throwaway immediately before the take, then `make recording-reset`.
- **Two affected grants costs ~7 s, not ~2.4 s.** One uncached Gemini notice-drafting call per
  affected grant. Verify the affected set is 1 in pre-flight step 5. This is the single most likely
  way the hero beat goes wrong.
- **Both secrets.** Frames A/C need the counterparty key, Frame B needs the artist key, and neither
  is in the repo. Export them in a shell you never film, and check the frame before you roll.
- **The hero writes real events.** Re-seed between takes. If you take five takes you will have five
  revocation events in the log — that is fine and honest (append-only, all visible), but the "before"
  frame needs the grant active, so re-seed.
- **Do not open Frame A on the raw event dump.** `/api/v1/debug/compromised_agent_read` returned 6
  documents on 2026-08-08 and 16 on 2026-08-09, first line `SIG_REVOKED`, and it grows with every
  take. Frame A reads the fold (`permitted: true`), which is stable and is the better shot anyway.
- **Do not show `/console/` performing a revocation.** It is read-only; its button is a local
  preview and sends no request. Showing it as if it revoked would be the one dishonest frame in the
  video.
- **Say "policy identities," not "four service accounts running the agents."**
- **Say "one work verified, four asserted,"** not "five verified works."
