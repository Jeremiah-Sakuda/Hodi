import urllib.request
import json
import re
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

    SELF_DEPLOY_CHECK_USER_AGENTS = [
        r"python-urllib", r"curl", r"wget", r"gcloud", r"google-cloud-sdk", r"postmanruntime"
    ]

    THIRD_PARTY_BOT_USER_AGENTS = [
        r"gptbot", r"ccbot", r"claudebot", r"google-extended", r"bytespider",
        r"scrapy", r"ahrefsbot", r"semrushbot", r"dotbot", r"rogue-scraper",
        r"bingbot", r"googlebot", r"yandex", r"duckduckbot", r"slurp", r"facebookexternalhit"
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

        # 1. Whitelist self-originated deploy check traffic
        for pattern in self.SELF_DEPLOY_CHECK_USER_AGENTS:
            if re.search(pattern, ua_lower):
                return "self_deploy_check"

        # 2. Try local Ollama Gemma inference (Non-load-bearing!)
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
