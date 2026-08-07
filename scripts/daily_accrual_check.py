#!/usr/bin/env bash
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
    third_party_count = 0
    distinct_user_agents = set()

    SELF_UA_PATTERNS = ["python-urllib", "curl", "wget", "gcloud", "hodi-healthcheck"]

    for doc in docs:
        data = doc.to_dict()
        ua = data.get("user_agent", "unknown")
        host = data.get("hostname", "hodi-evidence-endpoint-406699565497.us-central1.run.app")
        distinct_user_agents.add(ua)

        hostname_breakdown[host] = hostname_breakdown.get(host, 0) + 1

        ua_lower = ua.lower()
        if any(p in ua_lower for p in SELF_UA_PATTERNS):
            self_originated_count += 1
        else:
            third_party_count += 1

    return {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_accrued_records": total_count,
        "self_originated_count": self_originated_count,
        "third_party_count": third_party_count,
        "distinct_user_agents": list(distinct_user_agents),
        "hostname_breakdown": hostname_breakdown
    }

if __name__ == "__main__":
    base_url = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
    verify_sitemap_and_robots(base_url)
    
    stats = audit_firestore_crawler_access()
    print("\n--- FIRESTORE CRAWLER ACCESS STATS ---")
    print(json.dumps(stats, indent=2))
