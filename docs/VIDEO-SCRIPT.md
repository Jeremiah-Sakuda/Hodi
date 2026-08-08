# Hodi — recording script

**Target 3:30 · hard cap 4:00 · 30 seconds of insurance**
Everything except the recording. All durations below are **measured**, not estimated — the source
for each is named. Re-measure with `make metrics` if you record more than a day from now.

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

| Action | Measured | Beat budget |
|---|---|---|
| Live revocation cascade | **295 / 322 / 294 ms** round-trip (measured 2026-08-08) | 45 s |
| Natural-language license | **3.30 / 3.41 / 3.30 s** round-trip (fresh) · 3175 ms avg in `metrics.json` | 35 s |
| Full boundary test, 6 denials | **9.7 s** cold, ~2.2 s warm | 20 s |
| `make demo`, all 7 beats | **1.4 – 1.8 s** | — |
| Quarantine drill | 1114 ms server-side; **7.3 s** cold / 1.5 s warm round-trip | 20 s |

So the hero beat is **not** 45 seconds of waiting. It is ~0.3 s of action wrapped in 45 s of
*before* and *after*: the grant standing, the command, the cascade output, the struck-through grant,
the receipt. Plan the shot as three static frames with one instant transition, not as a progress bar.

**Do not speed-ramp or cut mid-command.** The wall clock is the proof. If a command takes 300 ms,
show that it took 300 ms — it is a stronger claim than a long one.

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

4. **Seed the hero grant.** The cascade needs something real to revoke.
   ```bash
   python3 scripts/seed_demo_grant.py
   ```
   Expect: `Read-back verified: document exists with expected counterparty_id.`

5. **Confirm the deployed service answers and the boundary holds.**
   ```bash
   make demo-live
   ```
   Expect: **6 HTTP 403s** and `ALL LIVE BOUNDARY TESTS PASSED`.

6. **Warm the service** so Beat 3 doesn't eat a 7 s cold start on camera.
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://hodi-evidence-endpoint-406699565497.us-central1.run.app/
   ```
   Run this again within ~5 minutes of each take. Cloud Run has `min-instances=0`; if it idles, the
   next call pays the cold start.

7. **Have the artist credential in the shell** (needed for the hero beat). It is not in the repo:
   ```bash
   export HODI_ARTIST_KEY=key-artist-jeremiah
   export HODI_ARTIST_SECRET='<the secret printed when you seeded it>'
   ```
   **Do not let this scroll on screen.** Set it in a shell you never point the camera at, or set it
   before you start recording and clear the terminal.

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
python3 scripts/seed_demo_grant.py
```

It is idempotent (deterministic document id), so re-running restores the grant to active. Nothing
else needs resetting: `make demo` is offline and stateless, `make demo-live` writes nothing, and the
drill is structurally write-free.

**Never** point the hero at a work id you care about. `work-repo-001` is the seeded demo target.

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
import json, hmac, hashlib, time, urllib.request
from datetime import datetime, timezone
BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
KEY, SECRET = "key-acme-il", "<counterparty secret>"
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

**Measured: 3.30 / 3.41 / 3.30 s** round-trip, warm (2026-08-08). One server-side Gemini call.
**Burn in the wall clock.**

**On screen:** the plain-English request, then the returned `interpreted_scope`
(`fine_tuning` / `open_weights` / `["US","CA"]`), `interpreter_model: gemini-3.5-flash`, and the receipt.

**Say:** the buyer asks in English. Gemini 3.5 Flash structures it into a typed scope — and that is
*all* it does. The lattice decides permission, deterministically. An interpretation carrying
anything other than a valid scope is rejected, not coerced. **The model never grants anything.**

---

### Beat 4 — HERO: the revocation cascade · 45 s *(never cut)*

**Frame A (before, ~10 s).** Show the grant standing:
```bash
make demo-live 2>&1 | head -12
```
The `[A1]` block prints the live grant — `grant-acme-il-001`, `fine_tuning`, `open_weights`,
`["US","CA"]`.

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

**Measured: 295 / 322 / 294 ms** round-trip (2026-08-08). `metrics.json` records 467 ms cold /
287 ms warm for the cascade itself. **Burn in the wall clock — 300 ms is the point.**

**Frame C (after, ~25 s).** On screen, in the response:
- `derived_scopes` — `training`, `fine_tuning`, `rag_retrieval`, `human_reference`, walked from the
  lattice's covering relation, not enumerated in code
- `structured_derivation` — each step with its `parent` and the reason (`training ⊃ fine_tuning`)
- `affected_grants` — the grant, its counterparty, its original scope
- `issued_notices` — signed receipts

**Say:** one call. Containment resolves downstream scopes from the partial order. Signed notices and
receipts are issued. The original grant is **not deleted** — it is a new event that supersedes, and
the log still shows what was permitted yesterday. And the notice says the grant is terminated. It
does **not** say the model forgot anything, because a lint refuses to let it.

**Reset before the next take:** `python3 scripts/seed_demo_grant.py`

---

### Beat 5 — Security: the boundary, attacked live · 20 s

```bash
make demo-live
```
**Measured: 9.7 s cold, ~2.2 s warm.** Warm the service first (pre-flight step 6) or this beat
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
- **The artist secret.** Beat 4 needs it and it is not in the repo. Export it in a shell you never
  film, and check the frame before you roll.
- **The hero writes real events.** Re-seed between takes. If you take five takes you will have five
  revocation events in the log — that is fine and honest (append-only, all visible), but the "before"
  frame needs the grant active, so re-seed.
- **Do not show `/console/` performing a revocation.** It is read-only; its button is a local
  preview and sends no request. Showing it as if it revoked would be the one dishonest frame in the
  video.
- **Say "policy identities," not "four service accounts running the agents."**
- **Say "one work verified, four asserted,"** not "five verified works."
