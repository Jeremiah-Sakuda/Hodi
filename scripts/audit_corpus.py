import urllib.request
import json
import ssl
import sys

def check_url(url: str) -> dict:
    if url.startswith("oauth://"):
        return {"status": "unverifiable", "code": None}
    
    # Create an unverified context if needed, but standard is fine
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return {"status": "ok", "code": resp.status}
    except urllib.error.HTTPError as e:
        # 403 from medium/soundcloud often means bot protection, not missing
        # But for proof files, a 404 is a real failure.
        return {"status": "error", "code": e.code}
    except Exception as e:
        return {"status": "error", "code": str(e)}

# Re-evaluating the 5 works from main.py
works = [
    {
        "id": "work-essay-001",
        "uri": "https://medium.com/@jeremiahsakuda/consent-rails-and-creative-sovereignty",
        "tier": "verified_control",
        "proof_uri": "https://medium.com/@jeremiahsakuda/.well-known/hodi-proof.json"
    },
    {
        "id": "work-repo-001",
        "uri": "https://github.com/Jeremiah-Sakuda/Hodi",
        "tier": "verified_control",
        "proof_uri": "https://github.com/Jeremiah-Sakuda/Hodi/commit/7639226a1b2c3d4e5f60123456789abcdef01234"
    },
    {
        "id": "work-audio-001",
        "uri": "https://hodi-evidence-endpoint-406699565497.us-central1.run.app/works/audio-stems-2026",
        "tier": "verified_control",
        "proof_uri": "oauth://github/Jeremiah-Sakuda"
    },
    {
        "id": "work-essay-002",
        "uri": "https://jeremiahsakuda.com/drafts/multi-agent-consent-protocols",
        "tier": "asserted",
        "proof_uri": None
    },
    {
        "id": "work-audio-002",
        "uri": "https://soundcloud.com/jeremiahsakuda/bass-improvisations-2026",
        "tier": "asserted",
        "proof_uri": None
    }
]

print("=== CORPUS LIVE AUDIT ===")
for w in works:
    print(f"Work: {w['id']} (Tier: {w['tier']})")
    
    # Check URI
    uri_res = check_url(w['uri'])
    print(f"  URI ({w['uri']}): {uri_res['status']} ({uri_res['code']})")
    
    # Check Proof
    if w['proof_uri']:
        proof_res = check_url(w['proof_uri'])
        print(f"  Proof ({w['proof_uri']}): {proof_res['status']} ({proof_res['code']})")
    else:
        print("  Proof: None")
    
    print()
