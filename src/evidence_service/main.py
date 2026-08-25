import os
import socket
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore
from src.api.buyer_api import router as buyer_router
from src.gateway.gateway import GatewayPolicyDenial
from src.schema.scope import UseType
from pydantic import BaseModel
from opentelemetry import trace as otel_trace
from src.observability.tracing import active_exporter_kind

# Resolved once at import, the same way the provider resolved its exporter, so
# the middleware costs nothing on the console path.
_TRACE_FLUSH_NEEDED = active_exporter_kind() == "cloud_trace"

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("hodi-evidence-endpoint")

app = FastAPI(title="Hodi Evidence Endpoint", version="1.3.0")

# Import Buyer API
app.include_router(buyer_router)

@app.middleware("http")
async def flush_spans_before_the_instance_freezes(request: Request, call_next):
    """
    Push buffered spans to the durable backend before the response returns.

    WHY THIS IS NECESSARY AND WAS NOT OBVIOUS. `BatchSpanProcessor` flushes on a
    BACKGROUND THREAD. Cloud Run throttles a container's CPU to approximately
    nothing between requests, so that thread does not get scheduled: spans are
    created correctly, the exporter is built correctly, no error is logged
    anywhere — and nothing is ever written. Measured directly: with
    HODI_TRACE_EXPORT=cloud set and the exporter constructing without error,
    four real requests produced ZERO traces in the Cloud Trace API.

    That is the most dangerous shape a defect can take in this project: every
    component reports success and the claim is still false. The fix is one
    bounded flush inside the request, where CPU is guaranteed.

    It is a no-op unless the cloud exporter is actually the active one, so the
    credential-free offline path and the console exporter are untouched.
    """
    response = await call_next(request)
    if _TRACE_FLUSH_NEEDED:
        try:
            provider = otel_trace.get_tracer_provider()
            if hasattr(provider, "force_flush"):
                # Bounded: a slow trace backend must never hold a licensing
                # decision open. A dropped span is an observability loss; a
                # hung request is an outage.
                provider.force_flush(timeout_millis=2000)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Span flush failed, spans for this request may be lost: {e}")
    return response


@app.exception_handler(GatewayPolicyDenial)
async def gateway_policy_denial_handler(request: Request, exc: GatewayPolicyDenial):
    """
    HOD-312: a gateway denial is a structured event, never an unhandled 500.
    The response body carries the SAME PolicyDenialEvent that was logged, so the
    API's stated reason and the log's stated reason share one source.
    """
    return JSONResponse(
        status_code=403,
        content={
            "status": "DENIED",
            "error": str(exc),
            "denial_event": exc.denial.model_dump(mode="json")
        }
    )

# Mount Artist Console SPA
console_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "console")
app.mount("/console", StaticFiles(directory=console_dir, html=True), name="console")

# Removed mock grants for H7 (uses live Firestore data via AgentGateway)

# Initialize Firestore.
#
# Under a DECLARED offline run (HODI_OFFLINE=1) there is no client, and the
# handlers that need one already render "unavailable" rather than a plausible
# number (the Literal Metric Rendering Rule). Anything else — no credentials
# when none were declared — still raises at import, because a deployed
# evidence service that cannot reach Firestore must fail to start rather than
# serve an empty manifest that looks like a real one. Same fail-closed rule
# as the gateway (HOD-716); the only difference is that this module is also
# imported by the offline suite, which declares itself.
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
db = None if os.environ.get("HODI_OFFLINE") == "1" else firestore.Client(project=GCP_PROJECT)
COLLECTION_NAME = "crawler_access"

# Canonical Base URLs
CANONICAL_CUSTOM_DOMAIN = "https://hodi.jeremiahsakuda.com"
CANONICAL_RUN_DOMAIN = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"

def resolve_domain_host(domain_url: str) -> bool:
    """Checks whether custom domain host resolves via DNS. Returns False on NXDOMAIN."""
    try:
        host = domain_url.replace("https://", "").replace("http://", "").split("/")[0]
        socket.gethostbyname(host)
        return True
    except Exception as e:
        logger.warning(f"[DNS WARNING] Custom domain host '{domain_url}' did NOT resolve ({e}). Falling back to Cloud Run URL: {CANONICAL_RUN_DOMAIN}")
        return False

def get_effective_base_url() -> str:
    """
    Returns working HTTPS base URL.
    NEVER advertises an unreachable NXDOMAIN custom domain!
    Falls back to CANONICAL_RUN_DOMAIN if custom domain does not resolve.
    """
    env_override = os.environ.get("HODI_BASE_URL")
    if env_override and resolve_domain_host(env_override):
        return env_override.rstrip("/")

    if resolve_domain_host(CANONICAL_CUSTOM_DOMAIN):
        return CANONICAL_CUSTOM_DOMAIN

    return CANONICAL_RUN_DOMAIN

# Determine working active base URL
ACTIVE_BASE_URL = get_effective_base_url()
logger.info(f"Active Effective Base URL: {ACTIVE_BASE_URL}")

def seed_corpus_works() -> List[Dict[str, Any]]:
    """
    The COMMITTED SEED corpus (HOD-718): the author's five real registered
    works, kept in the repository so a clean clone serves a meaningful
    manifest with no database behind it. It is a labelled seed, NOT a
    stand-in — get_registered_works() unions it with everything actually
    registered through POST /api/v1/works and marks which is which.
    """
    base = get_effective_base_url()
    return [
        {
            "work_id": "work-essay-001",
            "artist_id": "artist-jeremiah",
            "medium": "prose",
            "title": "Consent Rails & Creative Sovereignty",
            "uri": "https://medium.com/@jeremiahsakuda/consent-rails-and-creative-sovereignty",
            "hodi_record_uri": f"{base}/works/work-essay-001",
            "content_hash": "f78a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f60123456789abcdef012345678",
            "control_tier": "asserted",
            "control_proof": None,
            "description": "Foundational essay on technical consent rails and institutional agent negotiations.",
            "published_at": "2026-08-04T00:00:00Z",
            "canary_string": "HODI-CANARY-20260806-PROSE-9F81A2B3C4",
            "canary_planted_at": "2026-08-06T12:40:00Z"
        },
        {
            "work_id": "work-repo-001",
            "artist_id": "artist-jeremiah",
            "medium": "code",
            "title": "Hodi Institutional Consent Fleet",
            "uri": "https://github.com/Jeremiah-Sakuda/Hodi",
            "hodi_record_uri": f"{base}/works/work-repo-001",
            "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "control_tier": "verified_control",
            "control_proof": {
                "method": "signed_commit",
                "verified_at": "2026-08-07T02:00:00Z",
                "evidence_uri": "https://github.com/Jeremiah-Sakuda/Hodi/commit/799eafc65104a936fc8b12ab715f126e0f687229",
                "metadata": {"author_identity": "jeremiahsomoine@gmail.com", "commit_sha": "799eafc65104a936fc8b12ab715f126e0f687229"}
            },
            "description": "Governed fleet of institutional agents administering creative consent.",
            "published_at": "2026-08-03T00:00:00Z",
            "canary_string": "HODI-CANARY-20260806-CODE-7639226A1B",
            "canary_planted_at": "2026-08-06T12:40:00Z"
        },
        {
            "work_id": "work-audio-001",
            "artist_id": "artist-jeremiah",
            "medium": "audio",
            "title": "Electric Bass Solo Recordings & Stems",
            "uri": f"{base}/works/audio-stems-2026",
            "hodi_record_uri": f"{base}/works/work-audio-001",
            "content_hash": "a1b2c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123",
            "control_tier": "asserted",
            "control_proof": None,
            "description": "Original electric bass audio recordings and multitrack stems.",
            "published_at": "2026-08-05T00:00:00Z",
            "canary_string": "HODI-CANARY-20260806-AUDIO-4C5D6E7F8A",
            "canary_planted_at": "2026-08-06T12:40:00Z"
        },
        {
            "work_id": "work-essay-002",
            "artist_id": "artist-jeremiah",
            "medium": "prose",
            "title": "Draft Notes on Multi-Agent Consent",
            "uri": "https://jeremiahsakuda.com/drafts/multi-agent-consent-protocols",
            "hodi_record_uri": f"{base}/works/work-essay-002",
            "content_hash": "b2c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123a1",
            "control_tier": "asserted",
            "control_proof": None,
            "description": "Unverified draft essay registered under asserted control tier for console multi-tier demonstration.",
            "published_at": "2026-08-06T10:00:00Z",
            "canary_string": "HODI-CANARY-20260806-PROSE-DRAFT-1A2B3C",
            "canary_planted_at": "2026-08-06T12:40:00Z"
        },
        {
            "work_id": "work-audio-002",
            "artist_id": "artist-jeremiah",
            "medium": "audio",
            "title": "Live Bass Improvisation Session",
            "uri": "https://soundcloud.com/jeremiahsakuda/bass-improvisations-2026",
            "hodi_record_uri": f"{base}/works/work-audio-002",
            "content_hash": "c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123a1b2",
            "control_tier": "asserted",
            "control_proof": None,
            "description": "Live electric bass recording registered under asserted tier.",
            "published_at": "2026-08-06T11:00:00Z",
            "canary_string": "HODI-CANARY-20260806-AUDIO-LIVE-3C4D5E",
            "canary_planted_at": "2026-08-06T12:40:00Z"
        }
    ]

def get_registered_works() -> List[Dict[str, Any]]:
    """
    The manifest: everything registered through POST /api/v1/works, unioned
    with the committed seed corpus (HOD-718).

    This used to BE the literal list. That made "register your work" a claim
    the running system could not honour — a new registration required a code
    change and a deploy — and it is the gap an external review named. Now a
    registration persists through the rights custodian and appears here.

    Two honesty properties:
      * every row carries `source`: "registered" (persisted through the API)
        or "seed_corpus" (committed in this repository). A reader can always
        tell which they are looking at.
      * if the registry is unreachable the seed is still served, but each row
        is marked `registry_unavailable` — the manifest never silently
        implies it is showing live state when it is not.
    """
    seed = {w["work_id"]: {**w, "source": "seed_corpus"} for w in seed_corpus_works()}
    try:
        from src.gateway.gateway import AgentGateway
        from src.schema.iam_policy import AGENT_SA_MAP
        rows = AgentGateway().read_collection(
            calling_sa=AGENT_SA_MAP["rights_custodian"]["sa_email"],
            calling_role_key="rights_custodian", target_collection="works")
    except Exception as e:
        logger.error(f"Works registry unavailable, serving the committed seed only: {e}")
        return [{**w, "registry_unavailable": True} for w in seed.values()]

    base = get_effective_base_url()
    merged = dict(seed)
    for r in rows:
        wid = r.get("work_id")
        if not wid:
            continue
        live = {k: v for k, v in r.items() if v is not None}
        prior = merged.get(wid, {})
        # A registered row wins FIELD BY FIELD, not row by row.
        #
        # This replaced the whole seed row, and that silently deleted every
        # field the persisted row did not happen to carry. The rows in Firestore
        # hold work_id/artist_id/control_tier; the seed holds those plus
        # canary_string, canary_planted_at, control_proof, title, uri,
        # content_hash, medium and published_at. So the live manifest served
        # five works with five fields each, no canaries, and — on the one
        # verified_control work — no control_proof, while /works/{id}/proof
        # returned HTTP 500. `verify_manifest.py` had been reporting exactly
        # this for as long as it was true; nothing ran it against the deployed
        # service until the live release-verification workflow first executed.
        #
        # Overriding what a row asserts is correct. Erasing what it is silent
        # about is not: absence is not an assertion.
        supplemented = sorted(k for k in prior
                              if k not in live and k not in ("source", "hodi_record_uri"))
        merged[wid] = {**prior, **live, "source": "registered",
                       "hodi_record_uri": f"{base}/{'works'}/{wid}"}
        # Never let a merged row read as though the artist registered fields
        # they did not. The provenance of every borrowed field is named.
        if supplemented:
            merged[wid]["seed_supplemented_fields"] = supplemented
    return list(merged.values())


def extract_client_ip(request: Request) -> str:
    """
    Returns the peer address as seen by the Cloud Run front end.

    X-Forwarded-For is APPENDED to by each proxy, so the LEFTMOST entry is
    whatever the client sent — fully attacker-controlled — and the rightmost
    entries are the ones added by infrastructure we trust. Reading [0], as this
    did, let anyone stamp a crawler_access record with an arbitrary source IP.
    On Cloud Run the client's real address is the LAST entry the front end
    appends, so we read from the right.

    This narrows forgery but does not eliminate it: a determined party can still
    choose their User-Agent, and `crawler_access` records are therefore treated
    as attributable-but-not-authenticated. That limit is stated in the README
    rather than papered over.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    if request.client and request.client.host:
        return request.client.host
    return "0.0.0.0"


# ---------------------------------------------------------------------------
# Evidence-domain access, through the gateway rather than a raw client.
#
# `crawler_access` and `accrual_audits` live in `hodi-evidence` now, and the
# front door deliberately holds NO grant there — that is the point of the split.
# These four call sites used the module-level `(default)` client directly, so
# after the migration they silently read an almost-empty collection and kept
# APPENDING new records to the database the data had just left. `/evidence-counts`
# reported 3 where the corpus is 1904, and the collection existed in two places
# at once, which is worse than either. Routing them through AgentGateway means
# the evidence service answers under its own identity and its own database.
# ---------------------------------------------------------------------------
def _evidence_gateway():
    from src.gateway.gateway import AgentGateway
    return AgentGateway()


EVIDENCE_SA = None  # resolved lazily; iam_policy is the source


def _evidence_sa() -> str:
    global EVIDENCE_SA
    if EVIDENCE_SA is None:
        from src.schema.iam_policy import AGENT_SA_MAP
        EVIDENCE_SA = AGENT_SA_MAP["evidence_agent"]["sa_email"]
    return EVIDENCE_SA


def evidence_read(collection: str, filters=None):
    return _evidence_gateway().read_collection(
        calling_sa=_evidence_sa(), calling_role_key="evidence_agent",
        target_collection=collection, filters=filters)


def evidence_counts(collections: list) -> dict:
    """Counts for several evidence collections in one hop when delegating."""
    from src.gateway.domain_client import DomainServiceClient
    domains = DomainServiceClient()
    if domains.handles("evidence_agent"):
        from src.gateway.domain_client import _post
        out = _post(domains._urls["evidence_agent"], "/internal/domain/counts",
                    {"role": "evidence_agent", "collections": list(collections)})
        return out.get("counts", {})
    counts = {}
    for c in collections:
        try:
            counts[c] = len(evidence_read(c))
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to count '{c}': {e}")
            counts[c] = "unavailable"
    return counts


def evidence_append(collection: str, record: dict) -> str:
    import uuid as _uuid
    doc_id = str(_uuid.uuid4())
    _evidence_gateway().write_document(
        calling_sa=_evidence_sa(), calling_role_key="evidence_agent",
        target_collection=collection, doc_id=doc_id, data=record)
    return doc_id


def check_robots_fetched_first(ip: str) -> bool:
    try:
        docs = evidence_read(COLLECTION_NAME, {"ip": ip, "path": "/robots.txt"})
        return len(docs) > 0
    except Exception as e:
        logger.error(f"Error checking robots.txt history: {e}")
        return False

def log_access_to_firestore(request: Request, path: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", request.headers.get("referrer", ""))
    hostname = request.headers.get("host", request.url.hostname or "unknown")
    
    robots_fetched = check_robots_fetched_first(ip)
    if path == "/robots.txt":
        robots_fetched = True

    record = {
        "timestamp": timestamp,
        "path": path,
        "user_agent": user_agent,
        "ip": ip,
        "referrer": referrer,
        "hostname": hostname,
        "robots_txt_fetched_first": robots_fetched,
        # An explicit UTC instant, not firestore.SERVER_TIMESTAMP. The sentinel
        # is resolved by the Firestore client at write time and cannot be JSON
        # -serialised, so it does not survive the hop to the evidence service —
        # it would fail the append rather than degrade, but the record is
        # clearer this way regardless: the time is the observing service's
        # clock, stated, rather than a value that means different things
        # depending on which process happened to write it.
        "logged_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        evidence_append(COLLECTION_NAME, record)
        logger.info(f"Access logged: host={hostname}, path={path}, ip={ip}, robots_first={robots_fetched}")
    except Exception as e:
        logger.error(f"Failed to log access to Firestore: {e}")

@app.middleware("http")
async def access_logging_middleware(request: Request, call_next):
    path = request.url.path
    log_access_to_firestore(request, path)
    response = await call_next(request)
    return response

@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots_txt(request: Request):
    base = get_effective_base_url()
    return f"""User-agent: *
Allow: /

Sitemap: {base}/sitemap.xml

# Hodi Creative Consent Terms
# Declared terms: {base}/.well-known/hodi.json
"""

@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def get_sitemap_xml(request: Request):
    base = get_effective_base_url()
    works = get_registered_works()
    urls = [
        f"{base}/",
        f"{base}/.well-known/hodi.json",
        f"{base}/robots.txt",
        f"{base}/works",
        f"{base}/canaries",
    ] + [f"{base}/works/{w['work_id']}" for w in works]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for url in urls:
        xml_lines.append(f'  <url><loc>{url}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')
    xml_lines.append('</urlset>')

    return Response(content="\n".join(xml_lines), media_type="application/xml")

@app.get("/.well-known/hodi.json", response_class=JSONResponse)
async def get_hodi_json(request: Request):
    base = get_effective_base_url()
    return {
        "hodi_version": "1.0",
        "publisher": "Jeremiah Sakuda",
        "repository": "https://github.com/Jeremiah-Sakuda/Hodi",
        "contact": "https://github.com/Jeremiah-Sakuda/Hodi/issues",
        "effective_base_url": base,
        "canonical_endpoints": {
            "custom_domain": CANONICAL_CUSTOM_DOMAIN,
            "cloud_run_domain": CANONICAL_RUN_DOMAIN
        },
        "default_policy": {
            "human_reference": "permitted",
            "rag_retrieval": "permitted",
            "fine_tuning": "negotiable",
            "training": "consent_required"
        },
        "robots_policy": f"{base}/robots.txt",
        "registered_works_manifest": f"{base}/works",
        "canaries_index": f"{base}/canaries",
        "terms_notice": "Access to registered works is logged and governed by Hodi consent protocols."
    }

@app.get("/", response_class=JSONResponse)
async def get_root(request: Request):
    base = get_effective_base_url()
    works = get_registered_works()
    return {
        "service": "Hodi Evidence Collection Endpoint",
        "status": "active",
        "effective_base_url": base,
        "registered_works": len(works),
        "manifest_url": f"{base}/works",
        "terms_url": f"{base}/.well-known/hodi.json",
        "robots_url": f"{base}/robots.txt",
        "sitemap_url": f"{base}/sitemap.xml"
    }

@app.get("/works", response_class=JSONResponse)
async def get_works(request: Request):
    works = get_registered_works()
    return {
        "count": len(works),
        "works": works
    }

@app.get("/works/{work_id}", response_class=JSONResponse)
async def get_work_by_id(work_id: str, request: Request):
    works = get_registered_works()
    for work in works:
        if work["work_id"] == work_id:
            return work
    raise HTTPException(status_code=404, detail="Work not found")

@app.get("/works/{work_id}/proof", response_class=JSONResponse)
async def get_work_proof(work_id: str, request: Request):
    works = get_registered_works()
    for work in works:
        if work["work_id"] == work_id:
            # .get(), not [] — a manifest row is not guaranteed to carry every
            # key, and this route answered HTTP 500 on the project's ONE
            # verified_control work because `control_proof` was absent rather
            # than None. A missing proof is a statable answer ("unverified"),
            # never a stack trace.
            if work.get("control_tier") != "verified_control" or work.get("control_proof") is None:
                return {
                    "work_id": work_id,
                    "control_tier": work.get("control_tier"),
                    "control_proof": None,
                    "status": "unverified",
                    "notice": "This work is registered under the 'asserted' tier without stored control proof (HOD-105)."
                }
            return {
                "work_id": work_id,
                "control_tier": work.get("control_tier"),
                "control_proof": work.get("control_proof"),
                "status": "verified"
            }
    raise HTTPException(status_code=404, detail="Work not found")

@app.get("/canaries", response_class=JSONResponse)
async def get_canaries(request: Request):
    works = get_registered_works()
    canaries = [
        {
            "work_id": w["work_id"],
            "title": w["title"],
            "canary_string": w["canary_string"],
            "planted_at": w["canary_planted_at"],
            "note": "Canary strings only protect content published after the planting date (2026-08-06)."
        }
        for w in works if w.get("canary_string")
    ]
    return {
        "count": len(canaries),
        "planted_date_utc": "2026-08-06T12:40:00Z",
        "limitation_notice": "Canaries protect work published after planting date only; retroactive detection of pre-existing scrapes is impossible.",
        "canaries": canaries
    }

SCHEDULER_INVOKER_SA = os.environ.get(
    "HODI_SCHEDULER_SA", "406699565497-compute@developer.gserviceaccount.com"
)


def expected_oidc_audiences(request: Request) -> set:
    """
    The audiences an inbound OIDC token may legitimately carry (HOD-743).

    WHY AN AUDIENCE CHECK IS NOT OPTIONAL. `verify_oauth2_token(token,
    Request())` with no audience verifies that Google signed the token and who
    the caller is — but NOT that the token was minted for THIS service. Any
    Google-signed ID token the same identity could obtain for any other audience
    satisfied every check these two routes made.
    `caller_identity.from_oidc()` has always passed an audience, with a
    paragraph explaining why; it simply is not on the deployed path, so the
    explanation lived in the repository and the check did not live in the
    service.

    WHY A SET, AND NOT `request.base_url`. Callers mint different, equally
    correct audiences:
      * Cloud Scheduler mints the FULL TARGET URL INCLUDING PATH
        (".../internal/accrual_audit") — verified against the live job config.
      * The front door mints the SERVICE ROOT when calling a domain workload
        (`fetch_id_token(..., url)` in src/gateway/domain_client.py).
    Pinning either one alone would have 403'd a caller that was doing exactly
    the right thing — and the scheduled audit is a capability this project
    reports as verified, so breaking it to add a security check would have
    traded one false claim for another.

    And why the canonical URL is included explicitly: the container runs uvicorn
    without `--proxy-headers`, so `request.base_url` reports the container's own
    bind address rather than the public host. Deriving the audience purely from
    the request would compare a public token against a private URL and refuse
    everything.
    """
    allowed = set()
    override = os.environ.get("HODI_OIDC_AUDIENCE")
    if override:
        allowed.add(override.rstrip("/"))

    path = request.url.path
    for base in {CANONICAL_RUN_DOMAIN, ACTIVE_BASE_URL, str(request.base_url).rstrip("/")}:
        base = base.rstrip("/")
        allowed.add(base)
        allowed.add(f"{base}{path}")
    return allowed


def _verified_oidc_claims(request: Request, token: str) -> dict:
    """
    Verify Google's signature, then check the audience OURSELVES.

    `verify_oauth2_token` accepts a single audience; the legitimate callers here
    use two different ones. So the signature and issuer are verified by the
    library, and the `aud` claim is compared against the allowed set explicitly
    — which also makes the refusal legible in the logs rather than a generic
    library error.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    claims = google_id_token.verify_oauth2_token(token, google_requests.Request())
    allowed = expected_oidc_audiences(request)
    aud = claims.get("aud", "")
    if aud not in allowed:
        logger.warning(
            f"OIDC audience rejected: token minted for '{aud}', which is not this service. "
            f"Allowed: {sorted(allowed)}")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")
    return claims


def verify_scheduler_oidc(request: Request) -> str:
    """
    Verifies the Google-signed OIDC ID token Cloud Scheduler sends, and returns
    the caller's email. Raises HTTPException(403) otherwise.

    The service itself must stay publicly reachable — its whole purpose is being
    crawled — so this route cannot be protected by Cloud Run IAM. It is
    protected in-process instead: only a token Google signed for our expected
    invoker service account gets through.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="Missing OIDC bearer token.")
    token = header.split(" ", 1)[1].strip()
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        claims = _verified_oidc_claims(request, token)
    except Exception as e:
        logger.warning(f"Accrual audit OIDC verification failed: {e}")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")

    email = claims.get("email", "")
    if not claims.get("email_verified") or email != SCHEDULER_INVOKER_SA:
        logger.warning(f"Accrual audit rejected caller '{email}'.")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")
    return email


def verify_front_door_oidc(request: Request) -> str:
    """
    Verify the caller of a domain operation is the front door (HOD-733).

    DEFENCE IN DEPTH, NOT THE ONLY DEFENCE. Domain services deploy with
    --no-allow-unauthenticated, so Cloud Run refuses anyone without
    roles/run.invoker before this code runs; that is the boundary. This check
    is the second one, in-process, so the service also refuses a caller that
    somehow holds invoker but is not the front door.

    Separate from verify_scheduler_oidc deliberately: that one pins the Cloud
    Scheduler invoker, and reusing it here would have made every domain call
    fail as the wrong caller, or — far worse if it had been written the other
    way — let the scheduler's identity perform domain writes.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="Missing OIDC bearer token.")
    token = header.split(" ", 1)[1].strip()
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        claims = _verified_oidc_claims(request, token)
    except Exception as e:
        logger.warning(f"Domain-operation OIDC verification failed: {e}")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")

    expected = os.environ.get("HODI_FRONT_DOOR_SA",
                              f"hodi-runtime-sa@{GCP_PROJECT}.iam.gserviceaccount.com")
    email = claims.get("email", "")
    if not claims.get("email_verified") or email != expected:
        logger.warning(f"Domain operation rejected caller '{email}' (expected '{expected}').")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")
    return email


class DomainOperation(BaseModel):
    role: str
    collection: str = ""
    collections: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    session_context: Optional[Dict[str, Any]] = None
    doc_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class InternalRevocationOperation(BaseModel):
    work_id: str
    revoked_use_type: UseType
    operation_id: Optional[str] = None


def _domain_service_or_404(req: "DomainOperation") -> str:
    """
    Establish the role THIS service is, and refuse anything else (HOD-733).

    The role is read from HODI_SERVICE_ROLE — set by the deploy, alongside the
    service account Cloud Run starts the container with — and NEVER from the
    request body. A caller may ask the custodian service for buyer terms; it
    will be refused, and it would be refused by IAM anyway, because this
    workload's identity is conditioned to its own database.

    This is the same correction the buyer API already carries for
    counterparty_id after the cross-buyer breach: identity is a property of the
    credential, not a field someone sends.
    """
    from src.gateway.domain_client import this_service_role
    role = this_service_role()
    if not role:
        # Not a domain service. The route does not exist here at all rather
        # than existing and refusing — a front door that answers domain
        # operations is the monolith this split removes.
        raise HTTPException(status_code=404, detail="Not found.")
    if req.role != role:
        logger.warning(
            f"DOMAIN_ROLE_REFUSED: this service is '{role}'; caller asked for '{req.role}'.")
        raise HTTPException(
            status_code=403,
            detail=f"This workload serves '{role}' only; it cannot act as '{req.role}'.")
    return role


@app.post("/internal/domain/read", response_class=JSONResponse)
async def domain_read(req: DomainOperation, request: Request):
    """A domain read, performed by the workload that owns the domain."""
    role = _domain_service_or_404(req)
    verify_front_door_oidc(request)
    from src.gateway.gateway import AgentGateway
    from src.schema.iam_policy import AGENT_SA_MAP
    docs = AgentGateway().read_collection(
        calling_sa=AGENT_SA_MAP[role]["sa_email"], calling_role_key=role,
        target_collection=req.collection, filters=req.filters,
        session_context=req.session_context)
    return {"role": role, "collection": req.collection, "documents": docs}


@app.post("/internal/domain/counts", response_class=JSONResponse)
async def domain_counts(req: DomainOperation, request: Request):
    """
    Count several collections of ONE domain in ONE round trip.

    /evidence-counts reports four evidence classes. Delegated one collection at
    a time that is four sequential authenticated HTTPS hops for a single public
    page — measured at ~3.7 s warm. All four live in the same database behind
    the same workload, so asking four times is purely our own doing. Each
    collection is still policy-checked individually; batching changes how many
    times we ask, never what is permitted.
    """
    role = _domain_service_or_404(req)
    verify_front_door_oidc(request)
    from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
    from src.schema.iam_policy import AGENT_SA_MAP
    gw = AgentGateway()
    out = {}
    for collection in (req.collections or []):
        try:
            out[collection] = len(gw.read_collection(
                calling_sa=AGENT_SA_MAP[role]["sa_email"], calling_role_key=role,
                target_collection=collection))
        except GatewayPolicyDenial:
            # A denial is an ANSWER about that collection, and it must not take
            # the other three down with it.
            out[collection] = "denied"
        except Exception as e:  # noqa: BLE001
            logger.error(f"count failed for '{collection}': {e}")
            out[collection] = "unavailable"
    return {"role": role, "counts": out}


@app.post("/internal/domain/write", response_class=JSONResponse)
async def domain_write(req: DomainOperation, request: Request):
    """A domain append, performed by the workload that owns the domain."""
    role = _domain_service_or_404(req)
    verify_front_door_oidc(request)
    if not req.doc_id or req.data is None:
        raise HTTPException(status_code=422, detail="doc_id and data are required.")
    from src.gateway.gateway import AgentGateway
    from src.schema.iam_policy import AGENT_SA_MAP
    AgentGateway().write_document(
        calling_sa=AGENT_SA_MAP[role]["sa_email"], calling_role_key=role,
        target_collection=req.collection, doc_id=req.doc_id, data=req.data)
    return {"role": role, "collection": req.collection, "doc_id": req.doc_id, "status": "APPENDED"}


@app.post("/internal/revocation/execute", response_class=JSONResponse)
async def execute_private_revocation(req: InternalRevocationOperation, request: Request):
    """Execute the mutating cascade only inside the propagator workload.

    Cloud Run IAM rejects anonymous callers first; this handler then pins the
    workload role from its environment and verifies the front door's OIDC
    identity.  The response carries an explicit surface marker so the caller
    cannot mistake an unrelated HTTP 200 for execution by this worker.
    """
    role = _domain_service_or_404(DomainOperation(
        role="revocation_propagator", collection="grants"))
    if role != "revocation_propagator":
        raise HTTPException(status_code=404, detail="Not found.")
    verify_front_door_oidc(request)

    from src.agents.revocation_propagator import RevocationPropagatorAgent
    from src.gateway.gateway import AgentGateway

    result = RevocationPropagatorAgent(
        gateway=AgentGateway(), memory_bank_events=[]
    ).execute_revocation_cascade(
        work_id=req.work_id,
        revoked_use_type=req.revoked_use_type,
        operation_id=req.operation_id,
    )
    return {
        "execution_surface": "private-revocation-worker",
        "result": result.model_dump(mode="json"),
    }


@app.get("/internal/accrual_audit", response_class=JSONResponse)
async def run_accrual_audit(request: Request):
    """
    Daily accrual audit (HOD-320), invoked by Cloud Scheduler job
    `hodi-daily-accrual-audit`. Counts crawler_access records, classifies them
    with the Gemma triage engine (self / bot / human / unknown), and persists
    an audit document to `accrual_audits` so audit history accumulates
    alongside Scheduler execution history.

    Requires the Scheduler's verified OIDC identity: this route shipped public
    and appended a document on every anonymous call, which is both unbounded
    write amplification and a way to pollute the audit history the project
    presents as evidence (BUILD-LOG correction #6).

    Append-only, like the grant log it audits. Each run writes a NEW immutable
    document keyed by its own timestamp; nothing is ever overwritten. An earlier
    version keyed the document by UTC date and OVERWROTE on same-day re-run —
    which required `datastore.entities.update`, the one permission the runtime
    identity is deliberately denied so that history cannot be rewritten. Keying
    each run distinctly means the audit trail accumulates under create-only IAM,
    and the docstring's own "history accumulates" claim is finally true. Reads
    take the latest document; a same-day re-run adds a row, it does not mutate.
    """
    caller = verify_scheduler_oidc(request)
    from src.evidence.gemma_triage import GemmaTriageEngine
    try:
        docs = evidence_read(COLLECTION_NAME)
    except Exception as e:
        logger.error(f"Accrual audit failed to read crawler_access: {e}")
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(e)})

    engine = GemmaTriageEngine()
    distribution = {"self_deploy_check": 0, "bot": 0, "human": 0, "unknown": 0}
    hostnames = {}
    for rec in docs:
        cls = engine.triage_record(rec)
        distribution[cls] += 1
        host = rec.get("hostname", "unknown")
        hostnames[host] = hostnames.get(host, 0) + 1

    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    audit = {
        "audit_date_utc": audit_date,
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_accrued_records": len(docs),
        "routing_distribution": distribution,
        "third_party_attributable": distribution["bot"] + distribution["human"] + distribution["unknown"],
        "hostname_breakdown": hostnames,
        "triggered_by": caller,
    }
    try:
        # Append-only: a distinct id per run via .add() (create), never .set() on
        # a fixed id (which upserts and needs datastore.entities.update — the
        # permission the runtime identity is denied). The UTC date stays a
        # queryable field for "the audit(s) from day D".
        evidence_append("accrual_audits", audit)
    except Exception as e:
        logger.error(f"Accrual audit failed to persist: {e}")
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(e)})
    return {"status": "ok", **audit}

@app.get("/evidence-counts", response_class=JSONResponse)
async def get_evidence_counts(request: Request):
    """
    HOD-370: Returns evidence counts by class.
    Reads LIVE from Firestore to prevent static fabrication in UI.
    """
    # EVERY class is counted from its collection. `canary_hit`, `verbatim_match`
    # and `redistribution` were hard-coded zeros here — literals on a live
    # surface, which is exactly what the Literal Metric Rendering Rule forbids
    # and exactly the defect corrected in the console (BUILD-LOG correction #1).
    # If a canary hit were ever recorded, this endpoint would have kept saying 0.
    # An unreachable collection renders "unavailable", never a plausible number.
    class_collections = {
        "crawler_access": COLLECTION_NAME,
        "canary_hit": "canary_hits",
        "verbatim_match": "verbatim_matches",
        "redistribution": "redistribution_findings",
    }
    # Counted through the gateway, so each class is read from the database its
    # domain actually lives in. Reading the raw `(default)` client here survived
    # the migration and reported 7 crawler_access records against a corpus of
    # 1904 — a live surface confidently serving a number from the database the
    # data had just left. "unavailable" on failure, never a plausible number.
    try:
        by_collection = evidence_counts(list(class_collections.values()))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Evidence counts unavailable: {e}")
        by_collection = {}
    counts = {cls: by_collection.get(coll, "unavailable")
              for cls, coll in class_collections.items()}

    try:
        from src.gateway.prompt_inspector import PromptInspector
        engine = "local_regex_inspector"
    except Exception:
        engine = "local_regex_inspector"

    return {
        **counts,
        "inspector_engine": engine,
        "claim_limit": ("Counts are per evidence class and are never summed. There is no "
                        "cross-class total, and no class asserts training-set membership."),
    }


@app.get("/verification-key", response_class=JSONResponse)
async def get_verification_key(request: Request):
    """
    The PUBLIC verification key for signed receipts, notices, and incident
    manifests (HOD-706). Serving it is what makes a signature worth anything:
    the recipient verifies with a key that could never mint. Three honest
    states, never conflated:
      * KMS configured   → the production key, fetched from Cloud KMS.
      * ephemeral signer → the process key, LABELLED ephemeral: it dies with
        this instance and proves mechanism, not durable authority.
      * no signer        → said plainly; documents carry labelled placeholders.
    """
    from src.schema.signing import get_active_signer, EphemeralEd25519Signer, KmsSigner
    try:
        signer = get_active_signer()
    except Exception as e:
        return JSONResponse(status_code=503, content={
            "signing": "misconfigured", "error": str(e)})
    if signer is None:
        return {
            "signing": "not_configured",
            "public_key_pem": None,
            "claim_limit": ("No signing key is configured on this deployment. Signature "
                            "fields carry the labelled UNSIGNED_PLACEHOLDER value and "
                            "prove nothing — run scripts/setup_kms_signing.sh and set "
                            "HODI_SIGNING=kms to change that."),
        }
    if isinstance(signer, EphemeralEd25519Signer):
        return {
            "signing": "ephemeral",
            "algorithm": signer.ALG,
            "key_id": signer.key_id,
            "public_key_pem": signer.public_key_pem,
            "claim_limit": ("EPHEMERAL key: generated at process start, dies with this "
                            "instance. Signatures verify against this key for the life of "
                            "the process only — mechanism demonstration, not durable "
                            "authority."),
        }
    return {
        "signing": "kms",
        "algorithm": KmsSigner.ALG,
        "key_id": signer.key_id,
        "key_version": signer.key_version_name,
        "public_key_pem": signer.public_key_pem(),
        "claim_limit": ("Verify: canonical JSON of the document without its `signature` "
                        "field, SHA-256, ECDSA-P256 against this public key. The private "
                        "key never leaves Cloud KMS."),
    }
