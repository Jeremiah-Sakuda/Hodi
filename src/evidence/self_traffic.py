"""
src/evidence/self_traffic.py — the single list of user agents that are OUR OWN.

Every tool this project points at its own endpoint must be listed here. When a
self-originated UA is missing, its traffic is counted as third-party and the
project's signature finding — "I published machine-readable consent terms at a
discoverable endpoint and nobody asked" — becomes a fabricated positive.

This has now happened twice: first `python-requests` and `Hodi-Latency-Test`
(2026-08-07), then `Google-Cloud-Scheduler` — the project's OWN Cloud Scheduler
job being counted as a third-party crawler. Hence one list, imported by both the
audit script and the triage engine, rather than two lists that drift.
"""

SELF_ORIGINATED_UA_PATTERNS = [
    # generic client libraries and CLIs used by our scripts
    "python-urllib",
    "python-requests",
    "curl",
    "wget",
    "httpx",
    "postmanruntime",
    # Google Cloud tooling calling our own endpoints
    "gcloud",
    "google-cloud-sdk",
    "google-cloud-scheduler",
    "gcp-cloud-run",
]

# Every probe this project points at its own endpoint is named "Hodi-<something>".
# Enumerating them individually failed THREE times — python-requests and
# Hodi-Latency-Test (2026-08-07), Google-Cloud-Scheduler (2026-08-08), and
# Hodi-Adversarial-Audit (2026-08-08) — each time inflating the third-party
# count with our own traffic. A prefix rule cannot be forgotten when a new
# probe is added, which an enumeration demonstrably can.
SELF_ORIGINATED_UA_PREFIX = "hodi-"


def is_self_originated(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    if ua.startswith(SELF_ORIGINATED_UA_PREFIX):
        return True
    return any(pattern in ua for pattern in SELF_ORIGINATED_UA_PATTERNS)
