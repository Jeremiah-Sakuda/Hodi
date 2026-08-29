# Hodi — recording script (browser walkthrough)

**One browser tab. One URL. Five steps, six clicks. ~470 spoken words · lands ≈3:45 with the live pauses.**

The video is recorded against the guided walkthrough at
**https://hodi-evidence-endpoint-406699565497.us-central1.run.app/demo** — the third door on the
platform site at `/`. Nothing in it is simulated: every number, signature, and refusal on screen is
produced by the deployed service during the take.

---

## The numbers rule — read this first

**Read what is on the screen, not what is on this page.** Every figure the demo shows is generated
live or served from the committed, dated audit (`docs/metrics.json` via `/metrics-snapshot`) — the
same file this script, the README, and Diagram B are held to by `make check-docs`.

As of the **2026-08-29** audit, the screen will read: 6956 accrued access records behind the
scenes, of which **29** match a crawler signature — three distinct self-identifying crawler user
agents between 2026-08-11 and 2026-08-29, twenty-one of which fetched `/robots.txt`, and exactly
**one** of which, ever, fetched the machine-readable terms. If the audit has been regenerated since,
say the number on the screen and regenerate this file (`make metrics`, then update here) before
publishing.

If you cite the cascade benchmark anywhere, the measured figure is median **2389 ms** warm at real
corpus scale, recorded on revision hodi-evidence-endpoint-00059-z55. The demo shows its own live
wall clock — prefer the clock on screen.

Do not name crawler vendors on camera — they did nothing wrong, and the point is not who they are.

---

## Before you hit record

1. **Warm it.** Open the URL ~30 seconds early; the service scales to zero. Wait for the dot beside
   "Google Cloud" in the top bar to turn **green**, then reload once for a clean start.
2. **Full-screen the browser** (⌃⌘F). Hide the bookmarks bar — the page fills the viewport.
3. **Record the whole screen** at 1440×900 or larger.
4. **Verify three things are legible** at recording resolution: the `…run.app` host in the top bar,
   `gemini-3.5-flash · Vertex AI` on step 2, and the words **Cloud Trace** in the fleet result on
   step 4.

Your only controls: the primary button bottom-right (its label changes per step), plus four inline
buttons on step 4. Arrow keys also work.

---

## 1 · REGISTER · ~0:00–0:40

**Screen:** five works tagged `ASSERTED`; the visitor-log panel with the gold crawler count and
tally, and the terms-fetch count beneath it. Hold still; let the host in the top bar be readable.

> Put creative work on the internet — music, writing, code — and AI companies will crawl it. Your
> only control is robots.txt: a file that can say one thing — crawl, or don't. Not *what* a company
> may do with your work — "training yes, but don't clone my voice" — and it cannot take a yes
> back.
>
> I'm an independent musician and developer — I will never have a legal team or a licensing
> department. **Hodi is a fleet of AI agents, live on Google Cloud, acting as that department —
> for anyone.**
>
> Everything you're seeing is the deployed service — that address in the top bar is its Cloud Run
> URL. These five works are mine. The visits on this log are AI crawlers — nearly all asked only
> whether they could crawl. None could ask what they may *do* with the work.

**Do:** click **Continue →**

## 2 · LICENSE · ~0:40–1:10

**Screen:** the company's request as a large quote; terms animate in under
"read live by gemini-3.5-flash · Vertex AI"; a green **✓ Granted** badge.

> A company asks to license my work, in plain English. **Gemini 3.5, on Vertex AI**, turns the
> sentence into structured terms — fine-tuning, non-commercial, attribution required.
>
> One rule runs through everything: **the model interprets; it never decides.** Deterministic code
> compares those terms to my registered consent — and grants this request.

**Do:** click **Continue →**

## 3 · REVOKE · ~1:10–2:00 · THE HERO

**Screen:** four uses with green dots, `IN FORCE`; a dashed box for synthesis, *not granted here*;
the primary button is red: **STAMP · TAKE IT BACK**.

> The part no text file can do: I change my mind. One stamp.

**Do:** click **Stamp** — stay silent ~2 seconds while the clock fills and the dots strike through.

> That's not an animation — it's the live cascade, with its wall clock. Revoking training
> automatically withdraws the narrower uses inside it — and leaves untouched the one I never
> granted.
>
> It crossed the agent gateway, joined a permanent event log — the fleet's shared memory — and was
> signed by **Cloud KMS**. And the request granted a minute ago is now refused.

**Do:** click **Continue →**

## 4 · CERTIFICATE + FLEET + ATTACKS · ~2:00–3:05 — four clicks, pause between each

**① Press seal — verify** (seal turns green) **· ② Alter one character** (seal turns red):

> That notice is a certificate anyone can check — verified in your browser against the published
> key. Alter one character — void.

**③ Run the real fleet delegation, live** — let the six rows fill:

> Why five agents instead of one? **Conflict of interest.** The agent that negotiates licenses
> must never touch revocations — so each is a separate **ADK** agent with its own Google Cloud
> identity and database permissions, enforced by a gateway on every call — not by a prompt.
>
> Here it runs live: six delegation hops. The negotiator asks for data it shouldn't have —
> refused. One agent hangs — the supervisor quarantines it and reroutes the work. **A stuck agent
> cannot stall the system.** Every hop lands in Cloud Trace.

**④ Run the attacks against the live service** — six rows resolve to `403 · REFUSED`:

> A consent registry is worth attacking — so here are six real attacks, replayed live. Six
> refused.

**Do:** click **Continue →**

## 5 · DECLARATIONS · ~3:05–3:45

**Screen:** three refusals with red ✕ marks; the closing lines. Slow down here.

> Last: what Hodi refuses to claim. It will never say my work was in a model's training data — it
> cannot reliably know. It will never pretend revocation un-trains a model. A registry that
> flatters creators is worthless. **This one is built to be believed.**
>
> And none of it is specific to me: at this same address, any creator can register work in the
> Studio, any buyer can ask in their own words in the Market. Play both sides yourself, right
> now.
>
> Your voice deserves a door. **Hodi is the knock.**

---

## Rehearsal & risk

- **Run the full sequence live three times and time the slowest.** Record against that number.
- **If a rehearsal exceeds 3:50, cut in this order:** the attack beat down to "Six attacks, six
  refused." → "the fleet's shared memory" clause → the certificate beat down to "Verified. Altered —
  void."
- **Never cut:** the cold open, "the model interprets; it never decides," the why-five-agents
  sentence, the quarantine beat, the Cloud Run URL line, the final two lines.
- **Don't mouse-point while reading a long sentence.** Click, drop the cursor, then speak.
- **Don't edit around latency.** If a call is slow, that silence *is* the proof. If a call fails
  outright, reload — every visit gets a fresh isolated sandbox — and retake.
- **If Stamp says "reached its limit,"** reload for a new sandbox (8 signatures per session).
- **After upload:** check the YouTube/Vimeo URL logged out; confirm it is public and under 4:00.
  Add captions after; don't re-cut the timing.

## Why each beat is there (the judging criteria, answered out loud)

| Criterion | Where it is answered |
|---|---|
| Define the friction + value proposition | Cold open — the problem in three sentences, Hodi in one |
| "Unlikely Hero" outside corporate roles | "I will never have a legal team… for anyone" |
| "Complex enough to warrant multi-agent?" | "Why five agents instead of one? Conflict of interest." |
| Strict separation of concerns | "its own identity, its own database permissions… not a prompt" |
| Failure tolerance / recovery | hang → quarantine → reroute, stated as a rule |
| Google Cloud proof in the video | the `.run.app` URL, said aloud on camera |
| Gemini via Vertex AI + ADK (mandatory stack) | named aloud on steps 2 and 4, matching the screen |
| Unedited live execution | the wall clock, the deliberate silences, no cuts inside actions |
