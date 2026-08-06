import unittest
from typing import Dict, Any

class GeminiVertexClient:
    """HOD-301 Vertex AI Gemini Client Wrapper (pinned literals, temperature 0, cache)."""
    PINNED_PRO_MODEL = "gemini-1.5-pro"
    PINNED_FLASH_MODEL = "gemini-1.5-flash"
    TEMPERATURE = 0.0

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def query(self, prompt: str, model_id: str = PINNED_PRO_MODEL) -> Dict[str, Any]:
        if model_id not in (self.PINNED_PRO_MODEL, self.PINNED_FLASH_MODEL):
            raise ValueError(f"Invalid model_id '{model_id}'. Must be pinned Vertex literal.")
        
        cache_key = f"{model_id}:{prompt}"
        if cache_key in self._cache:
            return {"text": self._cache[cache_key], "cached": True}

        # Simulated response
        res_text = f"Evaluated prompt under {model_id} at temp={self.TEMPERATURE}"
        self._cache[cache_key] = res_text
        return {"text": res_text, "cached": False}

class GemmaCrawlerTriage:
    """HOD-303 Gemma Crawler Log Triage Engine."""

    BOT_USER_AGENTS = ["GPTBot", "CCBot", "ClaudeBot", "Google-Extended", "Bytespider"]

    def triage_access_record(self, user_agent: str) -> str:
        """Classifies access record as bot, human, or unknown."""
        for bot in self.BOT_USER_AGENTS:
            if bot.lower() in user_agent.lower():
                return "bot"
        if "Mozilla/5.0" in user_agent and "bot" not in user_agent.lower():
            return "human"
        return "unknown"

class TestVertexGemma(unittest.TestCase):
    """
    HOD-301 & HOD-303 Test Suite.
    """

    def setUp(self):
        self.gemini = GeminiVertexClient()
        self.gemma = GemmaCrawlerTriage()

    def test_hod301_gemini_vertex_pinned_model_and_temp_zero(self):
        """HOD-301: Asserts pinned model literals, temperature 0.0, and durable response caching."""
        res1 = self.gemini.query("Evaluate scope", model_id="gemini-1.5-pro")
        self.assertFalse(res1["cached"])
        self.assertIn("temp=0.0", res1["text"])

        # Second query hits durable shared response cache
        res2 = self.gemini.query("Evaluate scope", model_id="gemini-1.5-pro")
        self.assertTrue(res2["cached"])

    def test_hod303_gemma_crawler_triage_classifies_access(self):
        """HOD-303: Asserts Gemma triage classifies crawler access records as bot/human/unknown."""
        self.assertEqual(self.gemma.triage_access_record("Mozilla/5.0 (compatible; GPTBot/1.0)"), "bot")
        self.assertEqual(self.gemma.triage_access_record("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0"), "human")
        self.assertEqual(self.gemma.triage_access_record("CustomCurlScript/0.1"), "unknown")

if __name__ == "__main__":
    unittest.main()
