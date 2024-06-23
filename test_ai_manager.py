import unittest
from unittest.mock import Mock, patch

import anthropic
import openai

from ai_manager import AIManager, AnthropicAI, OpenAIGPT


class TestAIManager(unittest.TestCase):
    def setUp(self):
        self.mock_config_manager = Mock()
        self.mock_config_manager.get_ai_keys.return_value = {
            "anthropic": ["key1", "key2"],
            "openai": ["key3", "key4"],
        }
        self.mock_config_manager.get_ai_platforms.return_value = {
            "claude": {
                "provider": "anthropic",
                "model": "claude-3",
                "max_tokens": 4096,
            },
            "gpt4": {"provider": "openai", "model": "gpt-4", "max_tokens": 8192},
        }
        self.ai_manager = AIManager(self.mock_config_manager)

    def test_initialize_ai_platforms(self):
        self.assertEqual(len(self.ai_manager.ai_platforms), 4)
        self.assertIsInstance(self.ai_manager.ai_platforms[0], AnthropicAI)
        self.assertIsInstance(self.ai_manager.ai_platforms[2], OpenAIGPT)

    @patch("ai_manager.AnthropicAI.call_ai")
    @patch("ai_manager.OpenAIGPT.call_ai")
    def test_call_ai_rotation(self, mock_openai_call, mock_anthropic_call):
        mock_anthropic_call.side_effect = [anthropic.RateLimitError(), "Success"]
        mock_openai_call.side_effect = openai.RateLimitError()

        result = self.ai_manager.call_ai("Test prompt")
        self.assertEqual(result, "Success")
        self.assertEqual(self.ai_manager.current_platform_index, 1)

    # Add more tests as needed


if __name__ == "__main__":
    unittest.main()
