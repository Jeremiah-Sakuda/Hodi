# Social posts — Hodi

Created for the All Things Agentic Hackathon.

**The rule (verbatim from the official rules):** a maximum of **0.2 points** is added for social
promotion, on **X, LinkedIn, Instagram, or Facebook**. Posts on **X or LinkedIn must include the
hashtag `#AllThingsAgenticHackathon`**. The cap is 0.2 in total — posting to several platforms does
not stack, so **one qualifying post is enough**. No URL submission is required by the rules, but the
links are added below so a judge can find it without being told.

Neither post names a real company as a violator; every adversary in this project is fictional and
unnamed. The crawler figure is stated as this project states it everywhere else — *visits
identifying themselves as* AI crawlers, because a user agent is self-declared and is not an
authenticated identity.

---

## Primary post — LinkedIn (recommended)

> This month, 29 visits to my work identified themselves as AI crawlers. 21 checked whether they
> were allowed **in**. Exactly one, ever, read the published terms. And none could ask what they
> were allowed to **do** with the work.
>
> There was never a way to ask. So I built the way.
>
> **Hodi** is a governed fleet of AI agents that lets a creator license, refuse, and revoke how their
> work is used to train AI, where every boundary is enforced by Google Cloud IAM and cryptography
> rather than by a promise in a prompt.
>
> You can try it yourself right now, in your browser. Nothing is simulated:
> https://hodi-evidence-endpoint-406699565497.us-central1.run.app/
>
> Register a work (hashed in your browser, never uploaded). License it to yourself in plain English:
> Gemini interprets the sentence live on Vertex AI, and deterministic policy decides. Take it back:
> a real revocation cascade runs against the live service and returns a Cloud KMS signature you can
> verify in your own browser, then alter one character and watch it void. Run the real ADK fleet and
> watch a hung agent get quarantined and rerouted. Throw six anonymous attacks at the live routes
> and watch all six refused.
>
> Built on Google ADK, Gemini 3.5 Flash and Gemma via Vertex AI, Cloud Run, Firestore, Cloud KMS,
> Cloud Scheduler and Cloud Trace.
>
> What it will **not** tell you: whether your work is in a model's training data. Nobody can prove
> that today, so the schema physically cannot express the claim. Revocation withdraws permission
> going forward; it does not un-train a model. The system will not even flatter me: none of my own
> five registered works shows as "verified", because I have not cryptographically proven ownership
> yet, and it refuses to round up.
>
> I also kept a ledger of every place the system lied to me while I built it: 66 defects, nine
> classes, four that came back after being fixed once. The write-up:
> https://jeremiah-sakuda.github.io/Hodi/blog/seven-ways-to-lie-to-yourself-in-code.html
>
> Code, build log and every correction note: https://github.com/Jeremiah-Sakuda/Hodi
>
> #AllThingsAgenticHackathon

**Attach:** `docs/architecture/diagram_b_what_hodi_will_not_say.png` — the struck-through fifth
column is the most legible image the project has, and it carries the honesty thesis without a caption.

---

## Short variant — X

> 29 visits from self-identified AI crawlers hit my work this month.
>
> 21 asked if they could come in. Exactly one read the terms. None could ask what they may DO with it.
>
> So I built the place to ask. Live, nothing simulated:
> https://hodi-evidence-endpoint-406699565497.us-central1.run.app/
>
> #AllThingsAgenticHackathon

**Attach:** the same PNG.

---

## After posting

The rules do not require submitting the URL, but a judge should not have to hunt for it:

1. **`README.md`** → `## Published writing` → replace `<!-- POSTED-URL-1 -->` (LinkedIn) and
   `<!-- POSTED-URL-2 -->` (X), and delete the `*(not yet posted)*` markers.
2. **Devpost "Try it out" links panel** — one row per URL. This is a separate field from the
   description and is easy to miss.

Post the links inside the post itself rather than as a first comment; both platforms rank an
in-post link fine, and a judge following the trail should land on the demo, not on a comment thread.
