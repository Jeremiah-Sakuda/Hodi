import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from google.cloud import firestore

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("hodi-evidence-endpoint")

app = FastAPI(title="Hodi Evidence Endpoint", version="1.1.0")

# Initialize Firestore
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
db = firestore.Client(project=GCP_PROJECT)
COLLECTION_NAME = "crawler_access"

# HOD-009 & HOD-105 Registered Corpus Manifest (Jeremiah Sakuda)
# 3 works with verified_control (and stored control_proof), 2 works with asserted (control_proof=None)
REGISTERED_WORKS: List[Dict[str, Any]] = [
    {
        "work_id": "work-essay-001",
        "artist_id": "artist-jeremiah",
        "medium": "prose",
        "title": "Consent Rails & Creative Sovereignty",
        "uri": "https://medium.com/@jeremiahsakuda/consent-rails-and-creative-sovereignty",
        "content_hash": "f78a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f60123456789abcdef012345678",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "well_known_file",
            "verified_at": "2026-08-06T12:00:00Z",
            "evidence_uri": "https://medium.com/@jeremiahsakuda/.well-known/hodi-proof.json",
            "metadata": {"token_hash": "f78a9b0c1d2e3f4a5b6c7d8e9f0a1b2c"}
        },
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
        "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "signed_commit",
            "verified_at": "2026-08-06T12:00:00Z",
            "evidence_uri": "https://github.com/Jeremiah-Sakuda/Hodi/commit/7639226a1b2c3d4e5f60123456789abcdef01234",
            "metadata": {"author_identity": "jeremiahsomoine@gmail.com", "commit_sha": "7639226a1b2c3d4e5f60123456789abcdef01234"}
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
        "uri": "https://github.com/Jeremiah-Sakuda/Hodi/works/audio-stems-2026",
        "content_hash": "a1b2c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123",
        "control_tier": "verified_control",
        "control_proof": {
            "method": "platform_oauth",
            "verified_at": "2026-08-06T12:00:00Z",
            "evidence_uri": "oauth://github/Jeremiah-Sakuda",
            "metadata": {"platform": "github", "account_id": "Jeremiah-Sakuda"}
        },
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
        "content_hash": "c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123a1b2",
        "control_tier": "asserted",
        "control_proof": None,
        "description": "Live electric bass recording registered under asserted tier.",
        "published_at": "2026-08-06T11:00:00Z",
        "canary_string": "HODI-CANARY-20260806-AUDIO-LIVE-3C4D5E",
        "canary_planted_at": "2026-08-06T12:40:00Z"
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

Sitemap: {base_url}/sitemap.xml

# Hodi Creative Consent Terms
# Declared terms: {base_url}/.well-known/hodi.json
"""

@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def get_sitemap_xml(request: Request):
    base_url = str(request.base_url).rstrip("/")
    urls = [
        f"{base_url}/",
        f"{base_url}/.well-known/hodi.json",
        f"{base_url}/robots.txt",
        f"{base_url}/works",
        f"{base_url}/canaries",
    ] + [f"{base_url}/works/{w['work_id']}" for w in REGISTERED_WORKS]

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
        "canaries_index": f"{base_url}/canaries",
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

@app.get("/works/{work_id}/proof", response_class=JSONResponse)
async def get_work_proof(work_id: str, request: Request):
    for work in REGISTERED_WORKS:
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
    canaries = [
        {
            "work_id": w["work_id"],
            "title": w["title"],
            "canary_string": w["canary_string"],
            "planted_at": w["canary_planted_at"],
            "note": "Canary strings only protect content published after the planting date (2026-08-06)."
        }
        for w in REGISTERED_WORKS if w.get("canary_string")
    ]
    return {
        "count": len(canaries),
        "planted_date_utc": "2026-08-06T12:40:00Z",
        "limitation_notice": "Canaries protect work published after planting date only; retroactive detection of pre-existing scrapes is impossible.",
        "canaries": canaries
    }
