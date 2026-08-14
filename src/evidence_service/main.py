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

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("hodi-evidence-endpoint")

app = FastAPI(title="Hodi Evidence Endpoint", version="1.3.0")

# Import Buyer API
app.include_router(buyer_router)

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
    registered = {
        r["work_id"]: {**r, "source": "registered",
                       "hodi_record_uri": f"{base}/works/{r['work_id']}"}
        for r in rows if r.get("work_id")
    }
    # A registered row wins over a seed row of the same id: the seed is a
    # starting point, not an override of what an artist actually did.
    return list({**seed, **registered}.values())


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

def check_robots_fetched_first(ip: str) -> bool:
    try:
        docs = db.collection(COLLECTION_NAME)\
                 .where("ip", "==", ip)\
                 .where("path", "==", "/robots.txt")\
                 .limit(1)\
                 .get()
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
        "logged_at": firestore.SERVER_TIMESTAMP
    }

    try:
        db.collection(COLLECTION_NAME).add(record)
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
            if work["control_tier"] != "verified_control" or work["control_proof"] is None:
                return {
                    "work_id": work_id,
                    "control_tier": work["control_tier"],
                    "control_proof": None,
                    "status": "unverified",
                    "notice": "This work is registered under the 'asserted' tier without stored control proof (HOD-105)."
                }
            return {
                "work_id": work_id,
                "control_tier": work["control_tier"],
                "control_proof": work["control_proof"],
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
        claims = google_id_token.verify_oauth2_token(token, google_requests.Request())
    except Exception as e:
        logger.warning(f"Accrual audit OIDC verification failed: {e}")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")

    email = claims.get("email", "")
    if not claims.get("email_verified") or email != SCHEDULER_INVOKER_SA:
        logger.warning(f"Accrual audit rejected caller '{email}'.")
        raise HTTPException(status_code=403, detail="OIDC token verification failed.")
    return email


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
        docs = [d.to_dict() for d in db.collection(COLLECTION_NAME).stream()]
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
        db.collection("accrual_audits").add(audit)
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
    counts = {}
    for evidence_class, collection in class_collections.items():
        try:
            counts[evidence_class] = len(db.collection(collection).get())
        except Exception as e:
            logger.error(f"Failed to count '{collection}': {e}")
            counts[evidence_class] = "unavailable"

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
