import unittest
from unittest.mock import Mock, patch

import anthropic
import openai

from ai_manager import AIManager, AnthropicAI, OpenAIGPT


class TestAIManager(unittest.TestCase):
    def setUp(self):
        self.mock_config_manager = Mock()
        self.mock_config_manager.get_ai_platforms.return_value = [
            {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20240620",
                "keys": ["key1", "key2"],
            },
            {
                "provider": "openai",
                "model": "gpt-4",
                "keys": ["key3", "key4"],
            },
        ]
        self.mock_config_manager.get_value.return_value = 3
        self.ai_manager = AIManager(self.mock_config_manager, "balanced")

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
        self.assertEqual(self.ai_manager.platform_queue[0], self.ai_manager.ai_platforms[1])

    @patch("ai_manager.AnthropicAI.call_ai")
    @patch("ai_manager.OpenAIGPT.call_ai")
    def test_call_ai_all_platforms_exhausted(self, mock_openai_call, mock_anthropic_call):
        mock_anthropic_call.side_effect = anthropic.RateLimitError()
        mock_openai_call.side_effect = openai.RateLimitError()

        with self.assertRaises(Exception) as context:
            self.ai_manager.call_ai("Test prompt")

        self.assertTrue("All AI platforms exhausted" in str(context.exception))

    @patch("ai_manager.AnthropicAI.get_rate_limit_reset_time")
    @patch("ai_manager.OpenAIGPT.get_rate_limit_reset_time")
    def test_get_rate_limit_reset_time(self, mock_openai_reset, mock_anthropic_reset):
        mock_anthropic_reset.return_value = 30
        mock_openai_reset.return_value = 60

        anthropic_error = anthropic.RateLimitError()
        openai_error = openai.RateLimitError()

        self.assertEqual(self.ai_manager.ai_platforms[0].get_rate_limit_reset_time(anthropic_error), 30)
        self.assertEqual(self.ai_manager.ai_platforms[2].get_rate_limit_reset_time(openai_error), 60)

    @patch("ai_manager.AIManager.call_ai")
    def test_analyze_changes_and_update_readme(self, mock_call_ai):
        mock_call_ai.return_value = "SUMMARY:\nTest summary\n\nREADME_UPDATES:\nTest README updates"

        original_structure = {"file1.py": "content1"}
        new_structure = {"file1.py": "content2", "file2.py": "content3"}
        original_readme = "Original README"
        changes_summary = "Changes made"
        mock_prompt_manager = Mock()

        summary, readme_updates = self.ai_manager.analyze_changes_and_update_readme(
            original_structure,
            new_structure,
            original_readme,
            changes_summary,
            mock_prompt_manager
        )

        self.assertEqual(summary, "Test summary")
        self.assertEqual(readme_updates, "Test README updates")
        mock_prompt_manager.get_readme_update_prompt.assert_called_once()
        mock_call_ai.assert_called_once()

    @patch("ai_manager.AIManager.call_ai")
    def test_analyze_changes_and_update_readme_invalid_response(self, mock_call_ai):
        mock_call_ai.return_value = "Invalid response format"

        original_structure = {"file1.py": "content1"}
        new_structure = {"file1.py": "content2"}
        original_readme = "Original README"
        changes_summary = "Changes made"
        mock_prompt_manager = Mock()

        with self.assertRaises(ValueError) as context:
            self.ai_manager.analyze_changes_and_update_readme(
                original_structure,
                new_structure,
                original_readme,
                changes_summary,
                mock_prompt_manager
            )

        self.assertTrue("Failed to parse AI response" in str(context.exception))


if __name__ == "__main__":
    unittest.main()
