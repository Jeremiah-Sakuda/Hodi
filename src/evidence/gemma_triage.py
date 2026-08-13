import urllib.request
import json
import re

from src.evidence.self_traffic import SELF_ORIGINATED_UA_PATTERNS, is_self_originated
from typing import Dict, Any, List

class GemmaTriageEngine:
    """
    Gemma Triage Engine (HOD-303).
    Classifies crawler access records into routing distribution:
    - 'self_deploy_check' (excluded from evidence denominator: python-urllib, curl, gcloud)
    - 'bot' (third-party web crawler / AI scraper)
    - 'human' (browser access)
    - 'unknown' (unclassified user-agent)
    
    Gemma is NON-LOAD-BEARING: If Ollama/Gemma inference fails or is offline,
    the engine gracefully falls back to heuristic classification, ensuring evidence records are produced.
    """

    # Self-traffic classification is delegated to is_self_originated() rather
    # than re-iterating the pattern list here. Copying the list meant this
    # engine silently missed the `hodi-` PREFIX rule when that was added — the
    # same two-implementations-of-one-rule failure, one level down.
    SELF_DEPLOY_CHECK_USER_AGENTS = SELF_ORIGINATED_UA_PATTERNS  # kept for introspection

    # GENERIC crawler signatures, deliberately not a list of named companies.
    #
    # This was an enumeration of real vendors' crawler user agents. Two reasons
    # it is gone: this project's positioning rule is that no real company appears
    # as a violator anywhere in the repo, and an allow/deny list of known names
    # cannot see a crawler it has not been told about. Matching the convention
    # that crawlers actually follow — self-identifying as a bot, crawler, spider
    # or scraper in the user agent — is neutral and catches crawlers nobody has
    # heard of yet. It is NOT strictly broader: a tool that identifies only by
    # framework name (e.g. a bare "Scrapy/2.11") no longer matches. That is an
    # accepted trade, and it is stated rather than glossed, because a UA that
    # does not self-identify as a crawler is exactly the unattributed case this
    # project reports as unattributed instead of promoting to a finding.
    #
    # Verified against the live corpus on 2026-08-08: this change moves
    # known_crawler_ua_matches by zero. It was 0 before and 0 after.
    THIRD_PARTY_BOT_USER_AGENTS = [
        # `bot\b`, not `\bbot\b`. Requiring a word boundary BEFORE "bot" meant the
        # single most common crawler-naming convention — a vendor prefix glued
        # straight onto "bot" — did not match, so a real crawler that fetched
        # /robots.txt on 2026-08-11 was counted as unattributed and
        # known_crawler_ua_matches stayed 0. Anchoring only the trailing boundary
        # catches that whole family without naming any vendor.
        r"bot\b", r"bot/", r"[-_]bot", r"bot[-_]",
        r"crawler", r"spider", r"scraper", r"\bfetcher\b", r"\bindexer\b",
    ]

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host

    def triage_record(self, record: Dict[str, Any]) -> str:
        """
        Classifies record into 'self_deploy_check', 'bot', 'human', or 'unknown'.
        First checks self-originated deploy traffic, then attempts local Ollama Gemma inference,
        falling back to heuristic regex if offline.
        """
        user_agent = record.get("user_agent", "")
        ua_lower = user_agent.lower()

        # 1. Whitelist self-originated traffic — ONE implementation, shared with
        #    the accrual audit (src/evidence/self_traffic.py).
        if is_self_originated(user_agent):
            return "self_deploy_check"

        # 2. Try serverless Gemma on Vertex AI (gemma-4-26b-a4b-it-maas, pinned;
        #    probed reachable 2026-08-07 — see docs/FINDINGS.md). Non-load-bearing:
        #    any failure falls through to Ollama, then to the heuristic.
        try:
            from src.llm.vertex_gemini import VertexGeminiClient, PINNED_GEMMA_TRIAGE_MODEL
            response_text = VertexGeminiClient().generate(
                f"Classify this web access user-agent string as 'bot', 'human', or 'unknown'. "
                f"User-Agent: '{user_agent}'. Output single word classification only.",
                model_id=PINNED_GEMMA_TRIAGE_MODEL
            ).strip().lower()
            if "bot" in response_text:
                return "bot"
            elif "human" in response_text:
                return "human"
            elif "unknown" in response_text:
                return "unknown"
        except Exception:
            pass  # Gemma MaaS offline/unavailable — NON-LOAD-BEARING

        # 3. Try local Ollama Gemma inference (Non-load-bearing!)
        try:
            url = f"{self.ollama_host}/api/generate"
            payload = {
                "model": "gemma:2b",
                "prompt": f"Classify this web access user-agent string as 'bot', 'human', or 'unknown'. User-Agent: '{user_agent}'. Output single word classification only.",
                "stream": False
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "").strip().lower()
                if "bot" in response_text:
                    return "bot"
                elif "human" in response_text:
                    return "human"
                elif "unknown" in response_text:
                    return "unknown"
        except Exception:
            # Gemma offline / exception fallback — Gemma is NON-LOAD-BEARING!
            pass

        # 3. Heuristic regex fallback
        for pattern in self.THIRD_PARTY_BOT_USER_AGENTS:
            if re.search(pattern, ua_lower):
                return "bot"

        if "mozilla/5.0" in ua_lower:
            return "human"

        return "unknown"

    def triage_batch(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Triages a batch of access records and returns routing distribution metrics.
        Excludes self_deploy_check from third-party evidence denominator.
        """
        distribution = {
            "self_deploy_check": 0,
            "bot": 0,
            "human": 0,
            "unknown": 0
        }
        details = []

        for rec in records:
            cls = self.triage_record(rec)
            distribution[cls] += 1
            details.append({"record_id": rec.get("record_id", "unknown"), "classification": cls})

        sample_size = len(records)
        non_self_records = sample_size - distribution["self_deploy_check"]
        third_party_bot_count = distribution["bot"]

        return {
            "sample_size_total_requests": sample_size,
            "self_deploy_check_count": distribution["self_deploy_check"],
            "non_self_originated_requests_count": non_self_records,
            "routing_distribution": distribution,
            "details": details,
            "gemma_non_load_bearing_status": "operational_with_heuristic_fallback"
        }
