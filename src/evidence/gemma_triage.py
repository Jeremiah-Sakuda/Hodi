import urllib.request
import json
import re
from typing import Dict, Any, List

class GemmaTriageEngine:
    """
    Gemma Triage Engine (HOD-303).
    Classifies crawler access records as bot / human / unknown before Gemini evaluation.
    Developed against local Ollama (http://localhost:11434) with local heuristic fallback when Ollama is offline.
    Vertex AI endpoint proof happens once in Phase 4 and is torn down the same hour.
    """

    KNOWN_BOT_USER_AGENTS = [
        r"gptbot", r"ccbot", r"claudebot", r"google-extended", r"bytespider",
        r"python-urllib", r"curl", r"wget", r"scrapy", r"postman", r"ahrefsbot",
        r"semrushbot", r"dotbot", r"rogue-scraper"
    ]

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host

    def triage_record(self, record: Dict[str, Any]) -> str:
        """
        Classifies record into 'bot', 'human', or 'unknown'.
        First attempts local Ollama Gemma inference; falls back to exact regex heuristic if offline.
        """
        user_agent = record.get("user_agent", "")
        
        # Try local Ollama Gemma inference
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
            # Fall back to heuristic classification when Ollama is offline
            pass

        # Heuristic fallback matching HOD-303
        ua_lower = user_agent.lower()
        for pattern in self.KNOWN_BOT_USER_AGENTS:
            if re.search(pattern, ua_lower):
                return "bot"

        if "mozilla/5.0" in ua_lower and not any(re.search(p, ua_lower) for p in self.KNOWN_BOT_USER_AGENTS):
            return "human"

        return "unknown"

    def triage_batch(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Triages a batch of access records and returns volume reduction metrics."""
        results = {"bot": 0, "human": 0, "unknown": 0, "details": []}
        for rec in records:
            cls = self.triage_record(rec)
            results[cls] += 1
            results["details"].append({"record_id": rec.get("record_id", "unknown"), "classification": cls})

        total = len(records)
        bot_count = results["bot"]
        reduction_rate = (bot_count / total * 100.0) if total > 0 else 0.0

        results["summary"] = {
            "total_records": total,
            "bot_records": bot_count,
            "human_records": results["human"],
            "unknown_records": results["unknown"],
            "gemma_volume_reduction_rate_pct": round(reduction_rate, 2)
        }
        return results
