# Social posts — Hodi

Both posts name Hodi and carry the exact hashtag. Created for the All Things Agentic Hackathon.

---

## Post 1 — the teaser (defect-ledger angle)

> I built a system whose whole premise is refusing to claim what it can't verify.
>
> Then I kept a ledger of every place it lied to me anyway. 31 defects, 9 classes, 4 that came back after being fixed once.
>
> The worst one: my own Cloud Scheduler job was being counted as a third-party crawler — so the project's signature honesty finding had quietly inverted into a fabricated positive, manufactured by its own infrastructure.
>
> Hodi is a governed fleet of agents that administers creative consent. Four agents separated by conflict of interest, an append-only grant log, and honesty invariants enforced by schema rather than by good intentions.
>
> Full ledger, corrections included, in the write-up:
> https://jeremiah-sakuda.github.io/Hodi/blog/seven-ways-to-lie-to-yourself-in-code.html
>
> Code and build log: https://github.com/Jeremiah-Sakuda/Hodi
>
> #AllThingsAgenticHackathon

**Attach:** `docs/architecture/diagram_a_the_fleet.png`

---

## Post 2 — the launch (product angle)

> Your voice is in a product you never agreed to. There was no mechanism by which you could have agreed, refused, priced, or revoked.
>
> **Hodi is the knock.** *Hodi* is what you call at someone's door before entering.
>
> It's a governed fleet of agents administering creative consent end to end — register a work with proof of control, express scoped machine-readable terms, negotiate with a buyer under confidentiality, revoke and propagate. Ask in plain English; Gemini 3.5 Flash structures your request into a typed scope, and a deterministic lattice decides permission. The model interprets intent. It never grants anything.
>
> What Hodi will not tell you: whether your work was in a training set. That isn't determinable, there's no enum value for it, and the schema physically cannot express the claim. Revocation terminates a grant — it does not un-train a model.
>
> Built on ADK, Gemini 3.5 Flash and Gemma via Vertex AI, Firestore, Cloud Run and Cloud Scheduler. Open source, with the build log and every correction note.
>
> https://github.com/Jeremiah-Sakuda/Hodi
>
> Live consent terms, if you want to see what a machine-readable refusal looks like:
> https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json
>
> #AllThingsAgenticHackathon

**Attach:** `docs/architecture/diagram_b_what_hodi_will_not_say.png`

---

## Notes for posting

- Post 1 leads with the defect ledger, which is the most externally interesting artifact and travels well among engineers.
- Post 2 leads artist-side per the positioning rule, and states the honesty limits inside the post rather than only in the repo.
- Neither post names a real company as a violator; every adversary in this project is fictional and unnamed.

### Images to attach

| Post | Image | Why |
|---|---|---|
| **Post 1** | `docs/architecture/diagram_a_the_fleet.png` | Four agents behind four labelled conflict walls. It reads as an architecture claim, which is what an engineering audience is scrolling for. |
| **Post 2** | `docs/architecture/diagram_b_what_hodi_will_not_say.png` | The struck-through fifth column — the single most legible image the project has, and the one that carries the honesty thesis without a caption. |

Both PNGs are committed. Check the accrual figure on Diagram B still matches `docs/metrics.json`
before attaching — `make check-docs` guards the `.mmd` source, not the rendered PNG.

### Where the URLs go once posted

Three places, in this order:

1. **`README.md`** → `## Published writing` → the two placeholder lines. Replace
   `<!-- POSTED-URL-1 -->` with the LinkedIn URL and `<!-- POSTED-URL-2 -->` with the X URL, and
   delete the `*(not yet posted)*` markers.
2. **`docs/devpost-description.md`** → `## 4. Learnings` (the ledger paragraph names the blog;
   add the two post URLs alongside it) — then paste the updated section into the Devpost form,
   since Devpost does not read from the repo.
3. **The Devpost "Try it out" links panel** — one row per URL, labelled `LinkedIn` and `X`. This is
   separate from the description field and is easy to forget.

Post the blog link *inside* each post rather than as a first comment; both platforms rank a
link-in-post fine and a judge following the trail should land on the write-up, not on a comment
thread.
