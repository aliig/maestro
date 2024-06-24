import json
import re
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic
import openai
import tiktoken
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed


class AIInterface(ABC):
    @abstractmethod
    def call_ai(self, prompt: str, max_tokens: int) -> str:
        pass

    @abstractmethod
    def get_rate_limit_reset_time(self, error) -> float:
        pass


class AnthropicAI(AIInterface):
    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def call_ai(self, prompt: str, max_tokens: int) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=min(max_tokens, self.max_tokens),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def get_rate_limit_reset_time(self, error) -> float:
        if isinstance(error, anthropic.RateLimitError):
            headers = error.response.headers
            reset_time = headers.get("anthropic-ratelimit-reset")
            if reset_time:
                return max(
                    (
                        datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
                        - datetime.now(timezone.utc)
                    ).total_seconds(),
                    0,
                )
        return 60  # Default to 60 seconds if we can't determine the actual reset time


class OpenAIGPT(AIInterface):
    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def call_ai(self, prompt: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(max_tokens, self.max_tokens),
        )
        return response.choices[0].message.content

    def get_rate_limit_reset_time(self, error) -> float:
        if isinstance(error, openai.RateLimitError):
            headers = error.response.headers
            reset_time = headers.get("x-ratelimit-reset-requests")
            if reset_time:
                return max(float(reset_time) - time.time(), 0)
        return 60  # Default to 60 seconds if we can't determine the actual reset time


class AIManager:
    def __init__(self, config_manager, depth):
        self.config_manager = config_manager
        self.ai_platforms = self._initialize_ai_platforms()
        self.platform_queue = deque(self.ai_platforms)
        self.review_settings = config_manager.get_review_settings(depth)
        self.tokens_used = 0
        self.token_encoder = tiktoken.encoding_for_model("gpt-4")

    def _initialize_ai_platforms(self) -> List[AIInterface]:
        ai_platforms = []
        platforms = self.config_manager.get_ai_platforms()

        for platform in platforms:
            provider = platform["provider"]
            keys = platform["keys"]
            model = platform["model"]
            max_tokens = platform["max_tokens"]
            for key in keys:
                if provider == "anthropic":
                    ai_platforms.append(AnthropicAI(key, model, max_tokens))
                elif provider == "openai":
                    ai_platforms.append(OpenAIGPT(key, model, max_tokens))
                else:
                    raise Exception(f"Invalid AI provider: {provider}")

        return ai_platforms

    def _call_ai_with_retry(cls, platform, prompt: str, max_tokens: int):
        try:
            return platform.call_ai(prompt, max_tokens)
        except (anthropic.RateLimitError, openai.RateLimitError) as e:
            wait_time = platform.get_rate_limit_reset_time(e)
            print(
                f"Rate limit reached for {platform.__class__.__name__}. Waiting time: {wait_time:.2f} seconds."
            )
            time.sleep(
                min(wait_time, 60)
            )  # Wait for the shorter of wait_time or 60 seconds
            raise  # Re-raise the exception to trigger a retry
        except Exception as e:
            print(f"Error calling AI platform {platform.__class__.__name__}: {str(e)}")
            raise  # Re-raise the exception to trigger a retry

    def call_ai(self, prompt: str) -> str:
        if self.tokens_used >= self.review_settings["token_budget"]:
            raise Exception("Token budget exceeded. Review process halted.")

        max_tokens = min(
            self.review_settings["max_tokens_per_call"],
            self.review_settings["token_budget"] - self.tokens_used,
        )

        for _ in range(len(self.ai_platforms)):
            current_platform = self.platform_queue[0]
            try:
                result = self._call_ai_with_retry(current_platform, prompt, max_tokens)
                self.tokens_used += self._estimate_tokens(
                    prompt
                ) + self._estimate_tokens(result)
                return result
            except Exception:
                self.platform_queue.rotate(-1)  # Move the current platform to the end

        raise Exception("All AI platforms exhausted. Unable to complete the request.")

    def _estimate_tokens(self, text: str) -> int:
        return len(self.token_encoder.encode(text))

    def analyze_changes_and_update_readme(
        self, original_structure, new_structure, original_readme, changes_summary
    ):
        prompt = f"""
        Compare the original project structure to the new project structure after AI code review:

        Original structure:
        {json.dumps(original_structure, indent=2)}

        New structure:
        {json.dumps(new_structure, indent=2)}

        Summary of changes made during the review:
        {changes_summary}

        Original README content:
        {original_readme}

        Based on these changes:
        1. Provide a concise summary of the major changes made to the project.
        2. Suggest updates to the README.md file to reflect these changes. Consider:
           - New dependencies or requirements
           - Changes in project structure
           - Updates to usage instructions
           - Any new features or significant modifications

        Format your response as follows:

        SUMMARY:
        (Your summary of changes here)

        README_UPDATES:
        (Your suggested updates to the README here. Provide the full updated README content.)
        """

        response = self.call_ai(prompt)

        # Parse the response
        summary_match = re.search(
            r"SUMMARY:\n(.*?)\n\nREADME_UPDATES:", response, re.DOTALL
        )
        readme_match = re.search(r"README_UPDATES:\n(.*)", response, re.DOTALL)

        if summary_match and readme_match:
            return summary_match.group(1).strip(), readme_match.group(1).strip()
        else:
            raise ValueError(
                "Failed to parse AI response for changes summary and README updates"
            )
