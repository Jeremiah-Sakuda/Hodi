#!/usr/bin/env python3
# scripts/daily_accrual_check.py — Daily Accrual Audit & Sitemap URL Health Verification (HOD-320)
# Fetches robots.txt, sitemap.xml, verifies HTTP 200 status for all listed URLs, and updates metrics.json.

import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import subprocess
from google.cloud import firestore
from google.oauth2 import credentials

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
from src.evidence.self_traffic import SELF_ORIGINATED_UA_PATTERNS, is_self_originated
from src.evidence.gemma_triage import GemmaTriageEngine

def check_url_status_200(url: str) -> bool:
    """Fetches URL and asserts HTTP 200 status."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hodi-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[HEALTH CHECK FAIL] URL '{url}' returned error: {e}")
        return False

def verify_sitemap_and_robots(base_url: str):
    """Fetches robots.txt & sitemap.xml and asserts every URL returns HTTP 200 OK."""
    print(f"================================================================================")
    print(f"HODI DAILY ACCRUAL & SITEMAP HEALTH VERIFICATION")
    print(f"Base URL: {base_url}")
    print(f"================================================================================")

    # 1. Check robots.txt
    robots_url = f"{base_url}/robots.txt"
    assert check_url_status_200(robots_url), f"CRITICAL: robots.txt at '{robots_url}' failed HTTP 200 check!"
    print(f"[SUCCESS] robots.txt is live (HTTP 200): {robots_url}")

    # Fetch robots.txt body to parse Sitemap directive
    with urllib.request.urlopen(robots_url) as resp:
        robots_body = resp.read().decode("utf-8")
        sitemap_directive_url = None
        for line in robots_body.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_directive_url = line.split(":", 1)[1].strip()
                break

    assert sitemap_directive_url is not None, "CRITICAL: robots.txt contains NO Sitemap directive!"
    print(f"[SUCCESS] robots.txt specifies sitemap: {sitemap_directive_url}")

    # 2. Check sitemap.xml
    sitemap_url = f"{base_url}/sitemap.xml"
    assert check_url_status_200(sitemap_url), f"CRITICAL: sitemap.xml at '{sitemap_url}' failed HTTP 200 check!"
    print(f"[SUCCESS] sitemap.xml is live (HTTP 200): {sitemap_url}")

    # Fetch sitemap.xml and parse all <loc> entries
    with urllib.request.urlopen(sitemap_url) as resp:
        xml_content = resp.read().decode("utf-8")
        root = ET.fromstring(xml_content)
        # Handle XML namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [elem.text for elem in root.findall(".//sm:loc", ns)]

    print(f"Found {len(locs)} URLs in sitemap.xml. Verifying HTTP 200 status for each...")
    dead_urls = []
    for loc in locs:
        ok = check_url_status_200(loc)
        if ok:
            print(f"  [200 OK] {loc}")
        else:
            dead_urls.append(loc)

    assert len(dead_urls) == 0, f"CRITICAL: sitemap.xml contains {len(dead_urls)} dead URLs: {dead_urls}"
    print(f"[SUCCESS] ALL {len(locs)} sitemap URLs returned HTTP 200 OK!")

def audit_firestore_crawler_access() -> dict:
    """Queries crawler_access collection and returns hostname and self vs third-party breakdown."""
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token']).decode('utf-8').strip()
    creds = credentials.Credentials(token)
    db = firestore.Client(project="hodi-2026", credentials=creds)

    docs = list(db.collection("crawler_access").stream())
    
    total_count = len(docs)
    hostname_breakdown = {}
    self_originated_count = 0
    non_self_count = 0
    known_crawler_count = 0
    non_self_user_agents = {}
    distinct_user_agents = set()

    for doc in docs:
        data = doc.to_dict()
        ua = data.get("user_agent", "unknown")
        host = data.get("hostname", "hodi-evidence-endpoint-406699565497.us-central1.run.app")
        distinct_user_agents.add(ua)
        hostname_breakdown[host] = hostname_breakdown.get(host, 0) + 1

        if is_self_originated(ua):
            self_originated_count += 1
            continue

        non_self_count += 1
        non_self_user_agents[ua] = non_self_user_agents.get(ua, 0) + 1
        # The only number we are willing to call "a crawler": a user agent that
        # matches a KNOWN AI-crawler or search-crawler signature. Everything
        # else non-self is reported as unattributed, not promoted to a finding.
        if any(re.search(p, ua.lower()) for p in GemmaTriageEngine.THIRD_PARTY_BOT_USER_AGENTS):
            known_crawler_count += 1

    return {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_accrued_records": total_count,
        "self_originated_count": self_originated_count,
        "non_self_originated_count": non_self_count,
        "known_crawler_ua_matches": known_crawler_count,
        "non_self_user_agents": non_self_user_agents,
        "distinct_user_agents": list(distinct_user_agents),
        "hostname_breakdown": hostname_breakdown
    }

def verify_corpus_proofs(base_url: str):
    """Fetches /works manifest and re-verifies all verified_control evidence_uris."""
    print(f"\n================================================================================")
    print(f"HODI CORPUS PROOF VERIFICATION")
    print(f"================================================================================")
    
    works_url = f"{base_url}/works"
    try:
        req = urllib.request.Request(works_url, headers={"User-Agent": "Hodi-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            works = data.get("works", [])
    except Exception as e:
        assert False, f"CRITICAL: Failed to fetch /works manifest at '{works_url}': {e}"
        
    print(f"Found {len(works)} registered works. Auditing verified_control proofs...")
    
    dead_proofs = []
    for w in works:
        if w.get("control_tier") == "verified_control":
            proof = w.get("control_proof")
            if not proof:
                dead_proofs.append(f"{w['work_id']} (Missing proof object)")
                continue
            
            evidence_uri = proof.get("evidence_uri")
            if not evidence_uri:
                dead_proofs.append(f"{w['work_id']} (Missing evidence_uri)")
                continue
                
            if evidence_uri.startswith("http"):
                ok = check_url_status_200(evidence_uri)
                if ok:
                    print(f"  [200 OK] {w['work_id']} proof: {evidence_uri}")
                else:
                    dead_proofs.append(f"{w['work_id']} (Dead proof URI: {evidence_uri})")
            else:
                print(f"  [SKIPPED] {w['work_id']} proof is non-HTTP: {evidence_uri}")
                
    assert len(dead_proofs) == 0, f"CRITICAL: Found {len(dead_proofs)} broken verified_control proofs: {dead_proofs}"
    print(f"[SUCCESS] All verified_control works have live, resolving proof URIs!")

def write_metrics(stats: dict):
    """
    `make metrics` path: merges the freshly audited accrual stats into
    docs/metrics.json under 'daily_crawler_accrual_metrics'. Only this section
    is regenerated; every number in it is read from Firestore at audit time,
    never typed (Literal Metric Rendering Rule).
    """
    import os
    metrics_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "metrics.json")
    with open(metrics_path) as f:
        metrics = json.load(f)

    metrics["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics["daily_crawler_accrual_metrics"] = {
        "audit_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_accrued_records": stats["total_accrued_records"],
        "self_originated_count": stats["self_originated_count"],
        "non_self_originated_requests_count": stats["non_self_originated_count"],
        "known_crawler_ua_matches": stats["known_crawler_ua_matches"],
        "non_self_user_agents": stats["non_self_user_agents"],
        "distinct_user_agents_count": len(stats["distinct_user_agents"]),
        "distinct_user_agents": sorted(stats["distinct_user_agents"]),
        "hostname_breakdown": stats["hostname_breakdown"],
        "claim_limit": ("non_self_originated_requests_count counts requests this project did not "
                        "make; it is NOT a crawler count. known_crawler_ua_matches is the only "
                        "figure this project will describe as crawler access."),
    }

    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
    print(f"\n[make metrics] Regenerated 'daily_crawler_accrual_metrics' in {metrics_path} from live Firestore audit.")


if __name__ == "__main__":
    import sys
    base_url = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
    verify_sitemap_and_robots(base_url)
    verify_corpus_proofs(base_url)

    stats = audit_firestore_crawler_access()
    print("\n--- FIRESTORE CRAWLER ACCESS STATS ---")
    print(json.dumps(stats, indent=2))

    if "--write-metrics" in sys.argv:
        write_metrics(stats)
