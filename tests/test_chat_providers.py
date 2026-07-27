import os
import unittest
from unittest.mock import patch

from utils.chat_provider import provider_name
from utils.gemini_chat import GeminiClient, MODEL


class ChatProviderTests(unittest.TestCase):
    def test_gemini_is_default(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "gemini"}):
            self.assertEqual(provider_name(), "gemini")

    def test_opencode_remains_selectable(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "opencode"}):
            self.assertEqual(provider_name(), "opencode")

    def test_openrouter_is_selectable(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "openrouter"}):
            self.assertEqual(provider_name(), "openrouter")

    def test_unknown_provider_is_rejected(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "surprise-provider"}):
            with self.assertRaises(ValueError):
                provider_name()

    def test_gemini_payload_and_response_parser(self):
        client = GeminiClient(api_key="test-key")
        payload = client._payload("case context")
        self.assertEqual(MODEL, "gemini-2.5-flash")
        self.assertEqual(payload["generationConfig"]["temperature"], 0.2)
        data = {"candidates": [{"content": {"parts": [{"text": "Hello"}, {"text": " world"}]}}]}
        self.assertEqual(client._text_from_response(data), "Hello world")


if __name__ == "__main__":
    unittest.main()
