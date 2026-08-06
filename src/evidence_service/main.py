import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from google.cloud import firestore

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("hodi-evidence-endpoint")

app = FastAPI(title="Hodi Evidence Endpoint", version="1.0.0")

# Initialize Firestore
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
db = firestore.Client(project=GCP_PROJECT)
COLLECTION_NAME = "crawler_access"

# Registered works manifest (Author's published work: essays, repos, bass recordings)
REGISTERED_WORKS = [
    {
        "work_id": "work-essay-001",
        "title": "Essays & Technical Writing",
        "medium": "prose",
        "uri": "https://github.com/Jeremiah-Sakuda/Hodi/works/essay-001",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "well_known_file",
            "verified_at": "2026-08-06T00:00:00Z",
            "evidence_uri": "https://github.com/Jeremiah-Sakuda/Hodi"
        },
        "description": "Collection of published essays on governance, systems engineering, and consent rails."
    },
    {
        "work_id": "work-repo-001",
        "title": "Public Software Repositories",
        "medium": "code",
        "uri": "https://github.com/Jeremiah-Sakuda/Hodi",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "signed_commit",
            "verified_at": "2026-08-06T00:00:00Z",
            "evidence_uri": "https://github.com/Jeremiah-Sakuda/Hodi"
        },
        "description": "Open source codebases and system tools authored by Jeremiah Sakuda."
    },
    {
        "work_id": "work-audio-001",
        "title": "Bass Recordings & Audio Stems",
        "medium": "audio",
        "uri": "https://github.com/Jeremiah-Sakuda/Hodi/works/audio-001",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "well_known_file",
            "verified_at": "2026-08-06T00:00:00Z",
            "evidence_uri": "https://github.com/Jeremiah-Sakuda/Hodi"
        },
        "description": "Original electric bass audio recordings and performance stems."
    }
]

def extract_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
    
    robots_fetched = check_robots_fetched_first(ip)
    if path == "/robots.txt":
        robots_fetched = True

    record = {
        "timestamp": timestamp,
        "path": path,
        "user_agent": user_agent,
        "ip": ip,
        "referrer": referrer,
        "robots_txt_fetched_first": robots_fetched,
        "logged_at": firestore.SERVER_TIMESTAMP
    }

    try:
        db.collection(COLLECTION_NAME).add(record)
        logger.info(f"Access logged: path={path}, ip={ip}, robots_first={robots_fetched}")
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
    base_url = str(request.base_url).rstrip("/")
    return f"""User-agent: *
Allow: /

# Hodi Creative Consent Terms
# Declared terms: {base_url}/.well-known/hodi.json
"""

@app.get("/.well-known/hodi.json", response_class=JSONResponse)
async def get_hodi_json(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "hodi_version": "1.0",
        "publisher": "Jeremiah Sakuda",
        "repository": "https://github.com/Jeremiah-Sakuda/Hodi",
        "contact": "jeremiahsomoine@gmail.com",
        "default_policy": {
            "human_reference": "permitted",
            "rag_retrieval": "permitted",
            "fine_tuning": "negotiable",
            "training": "consent_required"
        },
        "robots_policy": f"{base_url}/robots.txt",
        "registered_works_manifest": f"{base_url}/works",
        "terms_notice": "Access to registered works is logged and governed by Hodi consent protocols."
    }

@app.get("/", response_class=JSONResponse)
async def get_root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "service": "Hodi Evidence Collection Endpoint",
        "status": "active",
        "registered_works": len(REGISTERED_WORKS),
        "manifest_url": f"{base_url}/works",
        "terms_url": f"{base_url}/.well-known/hodi.json",
        "robots_url": f"{base_url}/robots.txt"
    }

@app.get("/works", response_class=JSONResponse)
async def get_works(request: Request):
    return {
        "count": len(REGISTERED_WORKS),
        "works": REGISTERED_WORKS
    }

@app.get("/works/{work_id}", response_class=JSONResponse)
async def get_work_by_id(work_id: str, request: Request):
    for work in REGISTERED_WORKS:
        if work["work_id"] == work_id:
            return work
    raise HTTPException(status_code=404, detail="Work not found")
