---
layout: post
title: "Seven ways to lie to yourself in code"
description: "A defect ledger from building a system whose premise is refusing to assert what it cannot verify."
---

# Seven ways to lie to yourself in code

*Created for the All Things Agentic Hackathon.*

I built a system whose entire premise is refusing to assert what it cannot verify. Then I kept a ledger of every place it lied to me anyway.

The project is called Hodi — *hodi* is what you call at someone's door before entering. It's a governed fleet of agents that administers creative consent: registering works with proof of control, expressing machine-readable licensing terms, negotiating with buyers under confidentiality, propagating revocations. Four agents separated by conflict of interest, an append-only event log, and a set of honesty invariants that are supposed to be enforced by structure rather than by good intentions.

Over about seventy-two hours it produced fourteen real defects. They sort into seven classes. **Three of those classes recurred after being fixed once** — which is the actually interesting part, because a bug you fix twice is telling you something a bug you fix once is not.

Before the ledger, the one idea worth understanding, because most of what follows only lands if you have it.

The four agents are separated by **conflict of interest, not by task**. The rights custodian holds artist identity and must see it. The licensing negotiator talks to buyers and must *not* see other buyers' negotiated terms — rate confidentiality is the norm in licensing, and a leak destroys the next deal. The evidence agent reads access logs and outputs and must *not* see commercial terms, because findings from an agent that knows what a deal is worth are interested findings. The revocation propagator acts across grants and must not hold identity at all.

Stack those constraints and you get the point of the architecture: a single agent doing all four jobs would need the union of all four permission sets, which is precisely the position no honest broker may occupy. **A monolith here would itself be the violation.** The separation isn't decomposition for tidiness; it's the product. Which is why the first defect below is the one that matters most.

Here they are, worst first.

---

## The one that was live

The first invariant in the README reads: *"No agent can read another buyer's terms."* It's the first row of the invariant table, the reason there are four agents instead of one, and a beat in the demo video.

It was breakable over the public internet, unauthenticated, and it was broken.

`POST /api/v1/license` took `counterparty_id` from the request body and used that same value as **both** the database query filter **and** the "session context" the policy gateway validated that filter against. The gateway compared the caller's claim to itself and always agreed. The signature field was checked only for truthiness.

An unauthenticated request, naming a counterparty that was not its own, came back with that counterparty's grant id, their full negotiated scope, and a signed receipt issued in their name.

The gateway was working exactly as designed. It was being handed the attacker's assertion as ground truth. That's the shape of it: **the mechanism was fine, the input to the mechanism was the lie.**

The part that stings more is why the tests didn't catch it. There was a live boundary test. It passed the whole time. It exercised a debug endpoint that supplies its own session context — so it could not fail the way production failed.

> A boundary test that cannot fail the way production fails is not a boundary test.

And then, one day later, the same class again: `POST /api/v1/revoke`, three lines below the handler I'd just fixed, took no authenticator at all. Anyone could revoke any published work id. The response disclosed every affected counterparty's terms. And because the log is append-only with no update or delete permission, **the writes weren't undoable.**

I had fixed the reported route. I had not asserted the property across the routes.

---

## The one where my own infrastructure lied for me

Hodi's signature empirical finding is a negative result: *I published machine-readable consent terms at a discoverable endpoint and no crawler asked.* Nobody came. That absence is the evidence.

Its entire value depends on the third-party count being real.

The list of user agents belonging to my own tooling was missing one entry: `Google-Cloud-Scheduler`. From the moment I enabled the daily accrual job, **the project's own scheduled infrastructure was being counted as third-party crawler traffic.** The honesty finding had inverted into a fabricated positive, manufactured by the project itself.

It didn't surface from a test. It surfaced because the README said one number and the project's own documented `make metrics` command produced a different one. The docs and the tool disagreed, and the first thing a skeptical reader does is run the tool.

The root cause was duplication: the list existed in two files. And it had already fired once — the day before, with two different missing patterns. The fix that time was to add them to both copies. The comment directly above one of those lists literally warned that a missing pattern "inflates the third-party count into a fabricated finding."

The warning was correct. It did not prevent the recurrence. **A comment is not a mechanism.**

There's a coda. After fixing the list, ten non-self records remained. I nearly wrote them up as third-party hits. Then I looked: nine arrived within a single second, from cloud IPs, and one of them requested `/api/v1/debug/compromised_agent_read` — a path no sitemap advertises and no crawler would care about. That's someone inspecting the service. Not a crawler.

Reporting those ten as crawler access would have been exactly the fabricated finding the project exists to refuse, arrived at from the opposite direction. So the metric changed shape rather than value: there's now a field called `known_crawler_ua_matches`, currently zero, and it's the only number this project will describe as crawler access. Everything else non-self is labelled *unattributed*, with a note in the metrics file itself saying that a count of requests I didn't make is not a count of crawlers.

---

## The rest of the ledger

**Tests that could not fail.** Four of them. My favourite: the guardian of the append-only invariant — the property the entire audit trail rests on — built a set literal and asserted that the set contained what it had just been constructed to contain. It touched no policy, no role, no datastore. Elsewhere, prompt-injection detection lived entirely inside a test class gated behind a credentials flag, so emptying the detection patterns broke nothing; and a sort tiebreak documented as load-bearing for reproducibility was never exercised, because every fixture happened to carry a distinct timestamp.

**Infrastructure reported done, never built.** Budget alerts, a cost-fenced project, a scheduler. All written up as complete in the build log. None existed. This one gets its own correction note, because the pattern — reporting infrastructure as verified without an observed execution — is itself the finding.

**Claims with no code behind them.** Google's Agent Development Kit — ADK — was named as "the runtime agent framework" in the README, in the spec, and on the architecture diagram, while `google.adk` appeared nowhere in the codebase. The only occurrence of the string was inside a `print()` statement. It was my claim and my omission, so there is nobody to be vague about.

**Policy looser than the policy text.** Collection permissions were matched by prefix, so an entry written to express *per-counterparty scoping* also permitted reading the entire collection. And a `denied_collections` list sat in the policy data, consulted by nothing. The policy document was right. The generated documentation rendered it faithfully. The enforcement quietly did not implement it.

**Semantics that disagreed with themselves.** Four instances. The cleanest: a "superseded" grant. `resolve()` reported status *superseded* while handing back a live scope; the folded-state function correctly returned nothing; and the containment engine accepted the raw event and said *yes*. Three components, three answers, about the same event. Fail-closed, so never a breach — but "revocation is a new event that supersedes" was not what the read path implemented.

---

## The one claim that was verified before it was made

There is a counter-example in the ledger, and it is the same discipline applied one level up — to a decision about what to build on, rather than to code already written.

The competition spec required at least one Google agent framework. I intended to use the Antigravity SDK. Before building anything on it, I wrote down a boolean assertion and gave it a date:

> *From a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying (a) the invoking agent's identity, (b) the policy consulted, and (c) the outcome.*

Partial emission counted as a failure, stated in advance. Spans without agent identity cannot support the observability requirement, so "it emits spans, just not those ones" was defined as a no before there was any temptation to call it a yes.

The harness was two trivial agents, one delegating to the other, deployed as a Cloud Run Job under two distinct service accounts. Observed result: it failed at the first check — `No module named 'google.antigravity'`. The SDK does not currently expose a headless server-side Python surface for multi-agent delegation under distinct service accounts.

The pre-committed branch was ADK, and ADK is what runs today. The full assertion, the verbatim output, the span payloads and the branch taken are in [`docs/antigravity/decision.md`](../antigravity/decision.md).

I am not making a claim about the SDK's quality — this is one assertion, on one date, about one surface, and an IDE-oriented tool not having a headless server module is a reasonable thing for it to be. The part worth noticing is procedural: **the decision criterion existed before the test, so the outcome was executed rather than debated.** There was no afternoon spent negotiating with myself about whether partial emission was good enough.

And it is the only claim in this project that was verified before it was made. It is also the only one that never had to be corrected.

---

## The meta-pattern

Every one of these is the same failure at a different altitude:

> **A stated property, a mechanism that doesn't enforce it, and nothing connecting the two.**

The property is always written down somewhere — a README row, a docstring, a comment, a spec requirement. The mechanism usually exists too. What's missing is the wire between them: something that fails, loudly, when they come apart.

I already had one instance of that wire and it worked perfectly. The IAM conflict matrix in the docs is *generated* from the policy module the gateway reads. It cannot drift. In seventy-two hours it never drifted once.

Everywhere I hadn't built that wire, things drifted.

Worth saying plainly: much of this was built with agentic assistance, and several classes in this ledger are that practice's characteristic failure modes — infrastructure reported done without an observed execution, tests that assert what they were just constructed to assert, transcripts written rather than captured. The speed is real and so is that failure surface. The guards are the answer to it specifically: **a mechanism that fails loudly is the only thing that distinguishes work verified from work reported as verified.** Reading more carefully does not scale; a build that goes red does.

So the fixes that matter aren't the fourteen patches. They're the four guards:

- **One list, two consumers.** The self-traffic user agents live in one module now, imported by both the audit script and the triage engine. The duplication that caused the same defect twice is gone.
- **Docs must equal the tool.** A check fails the build if any number in the README or the diagrams disagrees with the regenerated metrics file. Prose and tool cannot silently diverge again.
- **Every pinned model needs a call site.** A test that fails if a model is declared but never called — because I'd pinned one that nothing invoked, which reads as model-count padding to anyone paying attention.
- **Every mutating route must authenticate.** The newest one, and the one I should have written first. It enumerates the router's own routes and fails CI if any POST, PUT, PATCH or DELETE reaches an endpoint that never authenticates. Exemptions go in a named list, in the diff, with a written reason. It's mutation-verified: I added a fake unauthenticated route and watched it fail.

That last guard is twenty lines. Both live security defects would have been caught by it, on the first commit, before either reached a deployed service.

---

## What I'd take from this

Generation-from-source is the strongest idea in this codebase, and I underused it. But it has a limit worth naming precisely:

**It protects against the documentation drifting from the source. It does not protect against the source being read wrongly.**

The conflict matrix was generated correctly from a policy module whose *enforcement function* matched collections by prefix. The document was accurate. The permission it described was not the permission being granted. Generation gives you consistency between artifacts; it gives you nothing about whether the shared artifact means what you think.

For that you need the second thing: a test that fails when the property is false, written from the property rather than from the implementation. Which is the standard advice, and I'd read it many times, and I still wrote four tests that couldn't fail.

The difference between knowing that and doing it, it turns out, is roughly one defect ledger.

---

None of which is why the thing exists.

An illustrator cannot currently say *this series may be trained on, that one may not, and this third may for a fee with attribution* in any form a counterparty can read, verify, or be held to. The options are a checkbox on a platform you don't control, a `robots.txt` line covering a whole domain, or a lawsuit years later. Buyers acting in good faith have the mirror problem: no way to find work that is actually licensable. Both sides are stuck for the same reason — there is no machine-readable, verifiable, revocable expression of creative consent. Hodi is an attempt at that rail: register a work with proof of control, express scoped terms a machine can read, ask in plain language and get a typed answer with a receipt, revoke and have it cascade.

And the finding I did not expect to be the most interesting one: I published machine-readable consent terms at a discoverable endpoint, with a `robots.txt` pointing at them, and **no crawler has asked.** Not one, across every access the endpoint has logged. The absence is the evidence. Hodi is the knock — it turns out the harder problem may not be building the door.

---

*Hodi is open source, with its full build log and findings — including every correction note quoted here. The two named findings above are in `docs/FINDINGS.md` in their complete form, with dates and exact exposure.*
