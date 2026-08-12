# Hodi — recording script

**Target 3:30 · hard cap 4:00 · 30 seconds of insurance**
Everything except the recording. All durations below are **measured**, not estimated — the source
for each is named. Re-measured against the deployed service on **2026-08-12**, revision
`00039-846`. Two correctness changes landed since 2026-08-10 and both are verified live: the
revocation cascade now terminates exactly the grants that **permit** the revoked use (it previously
ran backwards — see below), and `/api/v1/revoke` now checks the artist **owns** the work. The
boundary denial returns **6/6 HTTP 403 including Part C**; the hero cascade appends under create-only
IAM with the affected set, derived scopes and issued notices all correct; a non-owner revoke is
refused 403. Warm cascade ~0.5 s. Re-measure with `make metrics` if you record more than a day from now.

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

| Action | Measured (2026-08-09 unless noted) | Beat budget |
|---|---|---|
| Revocation cascade, **1 affected grant** | **461 / 496 / 506 / 644 ms** round-trip, ~519 ms avg (2026-08-12) | 45 s |
| Revocation cascade, **2 affected grants** | **5086 / 5275 / 4953 ms** — see the trap below | — |
| `POST /api/v1/license` (Frames A and C of the hero) | **399 ms** before · **399 ms** after (2026-08-10) | — |
| Natural-language license | **2.83 s** round-trip, warm (2026-08-10) · 3175 ms avg in `metrics.json` | 30 s |
| Full boundary test, 6 denials | **8.4 s** cold, ~2.2 s warm | 20 s |
| `make demo`, all 7 beats | **1.4 – 1.8 s** | — |
| Quarantine drill | 1114 ms server-side; **7.3 s** cold / 1.5 s warm round-trip | 20 s |

So the hero beat is **not** 45 seconds of waiting. It is ~0.5 s of action wrapped in 45 s of
*before* and *after*: the license granted, the command, the cascade output, the same license refused.
Plan the shot as three static frames with one instant transition, not as a progress bar.

### The 5-second trap in the hero beat — read this before the first take

The cascade's cost is **one Gemini notice-drafting call per affected grant that is not in the
committed response cache.** With one affected grant it is ~0.5 s. With two it is ~5.3 s, and it is
reproducibly ~5.3 s — not a cold start you can warm away.

`work-repo-001` carries two grants: `grant-acme-il-001` (the demo grant, cached, fast) and
`grant-seed-2` to `buyer-acme-2` (**not** cached — every revocation touching it pays a live model
call). As left on 2026-08-09, `grant-seed-2` is **revoked**, so the affected set is 1 and the beat is
fast. Pre-flight step 5 verifies this; do not skip it.

If you would rather show the cascade reaching two counterparties, that is a legitimate choice and the
story is arguably richer — but budget **5.3 s** of dead air, do not burn in a wall clock that
contradicts the "one call, instant" framing, and re-grant `grant-seed-2` first (snippet in
*Between takes*). **The recommendation is the one-grant shot.** The thesis of this beat is
containment across the *scope lattice* — all four use types derived from the partial order — and one
affected grant demonstrates that completely.

**Do not speed-ramp or cut mid-command.** The wall clock is the proof. If a command takes 500 ms,
show that it took 500 ms — a legal revocation cascading across the lattice in half a second is a
stronger claim than a long one.

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
   Expect: `RECORDING STATE READY — cascade on the ~0.5 s path.` If it says `~5.3 s`, the affected
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

**If you want the two-counterparty cascade instead** (and the ~5.3 s it costs), re-grant
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
tier is never hidden — one work is `verified_control` with a proof that resolves, four are
`asserted`, and the API says so rather than rounding up.

> Accuracy note: do **not** say "five verified works." One resolves. The README and Devpost both
> state this precisely; the video must match.

---

### Beat 2 — The four conflict walls · 20 s

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

> Say **"policy identities"** — the four SAs exist in GCP with the append-only role, but the
> deployed service is one Cloud Run process and the separation is enforced in-process. The README
> says this; the video must not imply four runtime principals.

---

### Beat 3 — The model interprets intent, the lattice decides · 30 s *(was 35)*

**Command** (paste as one block; it prints its own wall clock):
```bash
python3 - <<'EOF'
import json, hmac, hashlib, os, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = os.environ["HODI_CP_KEY"], os.environ["HODI_CP_SECRET"]
body = {"request_text": "We would like to fine-tune an open-weights model on this work "
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

**Measured: 2.83 s** round-trip, warm (2026-08-10); 3175 ms avg in `metrics.json`. One server-side Gemini call.
**Burn in the wall clock.**

**On screen:** the plain-English request, then the returned `interpreted_scope`
(`fine_tuning` / `open_weights` / `["US","CA"]`), `interpreter_model: gemini-3.5-flash`, and the receipt.

**Say:** the buyer asks in English. Gemini 3.5 Flash structures it into a typed scope — and that is
*all* it does. The lattice decides permission, deterministically. An interpretation carrying
anything other than a valid scope is rejected, not coerced. **The model never grants anything.**

---

### Beat 4 — HERO: the revocation cascade · 45 s *(never cut)*

**Frame A (before, ~10 s).** Do **not** dump the raw event log — it now holds 16 documents for this
counterparty and its first line is a `SIG_REVOKED` event from an earlier take, which is the worst
possible opening frame. Show the *answer* instead: ask for the licence and watch it be granted.

```bash
python3 - <<'EOF'
import json, hmac, hashlib, os, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = os.environ["HODI_CP_KEY"], os.environ["HODI_CP_SECRET"]
SCOPE = {"use_type": "fine_tuning", "model_class": "open_weights", "commercial": False,
         "attribution_required": True, "territory": ["US", "CA"], "valid_from": "2026-08-09T00:00:00Z"}
raw = json.dumps({"counterparty_id": "acme-intelligence-labs", "requested_scope": SCOPE,
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

**Measured: 399 ms, `permitted = True`**, with a receipt (2026-08-10). This frame is immune to log
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
EOF
```

**Measured: 461 / 496 / 506 / 644 ms** round-trip warm, ~519 ms average (2026-08-12), with one
affected grant. `metrics.json` records 3049 ms cold / 519 ms warm for the cascade itself. **Burn in
the wall clock — about half a second is the point.**

On screen, in the response:
- `derived_scopes` — `training`, `fine_tuning`, `rag_retrieval`, `human_reference`, walked from the
  lattice's covering relation, not enumerated in code
- `structured_derivation` — each step with its `parent` and the reason (`training ⊃ fine_tuning`)
- `affected_grants` — the grant, its counterparty, its original scope
- `issued_notices` — the notices and their receipts (the `signature` field reads
  `UNSIGNED_PLACEHOLDER:…` — say so, it is the honesty thesis in one field)

**Frame C (after, ~25 s).** Re-run **the Frame A command, unchanged.** Same request, same
counterparty, same scope.

**Measured: 399 ms, `permitted = False`** (2026-08-10).

> **Accuracy note (read once).** The demo grant is held at **`training`** (the broadest use),
> so revoking `training` correctly terminates it and the notice withdraws all four downstream
> uses. Do **not** seed it at a narrower use like `fine_tuning`: revoking `training` must NOT
> terminate a narrower grant, and `make recording-prep` seeds `training` for exactly this
> reason. The cascade selecting the wrong grants was the defect fixed on 2026-08-12.

**Say:** one call. Containment resolves downstream scopes from the partial order — `training` was
revoked, and `fine_tuning` fell with it because the lattice says `training ⊃ fine_tuning`, not
because anyone wrote that rule in code. Notices and receipts are issued — and their `signature` field
says `UNSIGNED_PLACEHOLDER`, because a signature only a service can verify is not a signature. The original grant is
**not deleted** — it is a new event that supersedes, and the log still shows what was permitted
before. And the notice says the grant is terminated. It does **not** say the model forgot anything,
because a lint refuses to let it.

> The A→C flip is the whole beat: *the identical request, granted and then refused, 400 ms apart.*
> That is worth more on camera than any amount of JSON, and it cannot be faked by a stub — the same
> endpoint answered both times.

**Reset before the next take:** `make recording-reset`

---

### Beat 5 — Security: the boundary, attacked live · 20 s

```bash
make demo-live
```
**Measured: 8.4 s cold (2026-08-09), ~2.2 s warm.** Warm the service first (pre-flight step 6) or this beat
overruns.

**On screen:** all three parts, ending on **6 × HTTP 403** and `ALL LIVE BOUNDARY TESTS PASSED`.

**Say:** Part A is the gateway policy layer. Part B replays the real cross-buyer exploit that worked
against this service on August 7th — unauthenticated, it read another counterparty's grant and got a
receipt. Part C replays anonymous revocation and an anonymous internal audit. All six refused. The
exploit is now a permanent regression test, and a test enumerates the router and fails CI if any new
mutating route forgets to authenticate.

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

**Say:** the worker is forced into an infinite loop. The supervisor bounds its own wait and writes
`TaskAbandoned` itself — the worker is still looping and has reported nothing. The registry
deregisters it for the rest of the run. The task reroutes to a standby that returns a **stated**
partial result and deliberately writes nothing, because the quarantined worker's write state is
unknown and the log is append-only. The request still completes.

---

### Beat 7 — Diagram B: the honesty beat · 15 s *(never cut)*

**On screen:** browser tab 4, `diagram_b_what_hodi_will_not_say.png`, full screen. Hold on the
struck-through fifth column.

**Say:** *"Here is what Hodi will not tell you."* Four typed evidence classes, no score, no total.
And a fifth column that does not exist: training-set membership. Not because we ran out of time —
because it is not determinable, there is no enum value for it, and the schema physically cannot
express the claim. Revocation terminates a grant. It does not un-train a model.

Then the measured negative: 539 accrued access records, **zero** matching any crawler signature.
I published machine-readable consent terms at a discoverable endpoint and nothing identifying itself
as a crawler has asked.

> Read those numbers off `docs/metrics.json` on the day you record. `make check-docs` keeps the
> README, the diagram and the submission text in agreement, but the diagram PNG is only as fresh as
> its last render.

---

### Beat 8 — GCP proof · 15 s

**On screen, in order, ~5 s each:**
1. Cloud Run → Revisions → the serving revision
2. Cloud Scheduler → both jobs `ENABLED` with **Last run** timestamps
3. GitHub → Actions → the green `verify` run

**Say:** deployed on Cloud Run, scale-to-zero. Two scheduled jobs with real execution history — the
nightly teardown has fired on its own cron. And every structural guard in the repo runs in CI on
every push.

---

### Beat 9 — Close · 10 s

**On screen:** the README title card, or the thesis lower-third.
**Say:** *Hodi* is what you call at someone's door before entering. **Hodi is the knock.**

---

## Budget

| # | Beat | Budget |
|---|---|---|
| 1 | Cold open — registered work | 15 s |
| 2 | Four conflict walls | 20 s |
| 3 | Model interprets, lattice decides | 30 s |
| 4 | **HERO — revocation cascade** | 45 s |
| 5 | Security — live boundary, 6 denials | 20 s |
| 6 | Quarantine and reroute | 20 s |
| 7 | **Diagram B — the honesty beat** | 15 s |
| 8 | GCP proof | 15 s |
| 9 | Close | 10 s |
| — | Transitions | 15 s |
| | **Total** | **205 s (3:25)** |

**Five seconds under the 3:30 target, 35 s under the hard cap.** The original §6 list came to 210 s
with a 35 s beat 3; the natural-language beat lands in 30 s because the command self-times.

**Nothing needs cutting.** But if you overrun on the day, use PRD §7's pre-committed order —
deepest reserve first, and do not improvise:

1. **GCP proof → 5 s** (revision + Scheduler in one frame; drop the CI tab) — **−10 s**
2. **Quarantine → 10 s** (the two transcript lines only, no setup) — **−10 s**
3. **Cold open → 10 s** (one burned-in stat card) — **−5 s**
4. **Conflict walls → 12 s** (hold Diagram A with narration over it) — **−8 s**

That is 33 s of reserve without touching the hero, the security beat, Diagram B, or the thesis.

**Never cut:** the revocation cascade at 45 s · the live boundary denials · Diagram B · the thesis at
0:08 and at close · the burned-in wall clock's continuity.

---

## Things that will bite you

- **Cold start.** `min-instances=0`. Any beat hitting the deployed service after ~15 minutes idle
  pays up to 7 s. Warm before every take.
- **Two affected grants costs ~5.3 s, not ~0.5 s.** One uncached Gemini notice-drafting call per
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
