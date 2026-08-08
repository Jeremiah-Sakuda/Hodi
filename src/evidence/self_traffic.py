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
    # this project's own named probes
    "hodi-healthcheck",
    "hodi-latency-test",
    "hodi-corpus-audit",
]


def is_self_originated(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return any(pattern in ua for pattern in SELF_ORIGINATED_UA_PATTERNS)
