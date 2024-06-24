import json
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic
import openai


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
    def __init__(self, config_manager, depth, ai_model):
        self.config_manager = config_manager
        self.ai_platforms = self._initialize_ai_platforms(ai_model)
        self.current_platform_index = 0
        self.review_settings = config_manager.get_review_settings(depth)
        self.tokens_used = 0

    def _initialize_ai_platforms(self, ai_model) -> List[AIInterface]:
        ai_platforms = []
        ai_keys = self.config_manager.get_ai_keys()
        platforms_config = self.config_manager.get_ai_platforms()
        print(platforms_config)

        if ai_model not in platforms_config:
            raise ValueError(f"Unsupported AI model: {ai_model}")

        config = platforms_config[ai_model]
        provider = config["provider"]
        api_keys = ai_keys[provider]
        model = config["model"]
        max_tokens = config["max_tokens"]

        if not isinstance(api_keys, list):
            api_keys = [api_keys]

        for api_key in api_keys:
            if provider == "anthropic":
                ai_platforms.append(AnthropicAI(api_key, model, max_tokens))
            elif provider == "openai":
                ai_platforms.append(OpenAIGPT(api_key, model, max_tokens))

        return ai_platforms

    def call_ai(self, prompt: str) -> str:
        if self.tokens_used >= self.review_settings["token_budget"]:
            raise Exception("Token budget exceeded. Review process halted.")

        max_tokens = min(
            self.review_settings["max_tokens_per_call"],
            self.review_settings["token_budget"] - self.tokens_used,
        )

        start_index = self.current_platform_index
        for _ in range(len(self.ai_platforms)):
            try:
                result = self.ai_platforms[self.current_platform_index].call_ai(
                    prompt, max_tokens
                )
                self.tokens_used += self._estimate_tokens(
                    prompt
                ) + self._estimate_tokens(result)
                return result
            except (anthropic.RateLimitError, openai.RateLimitError) as e:
                wait_time = self.ai_platforms[
                    self.current_platform_index
                ].get_rate_limit_reset_time(e)
                print(
                    f"Rate limit reached for API key {self.current_platform_index}. Waiting time: {wait_time:.2f} seconds."
                )

                # Move to the next API key
                self.current_platform_index = (self.current_platform_index + 1) % len(
                    self.ai_platforms
                )

                # If we've tried all keys and are back to the start, wait for the shortest reset time
                if self.current_platform_index == start_index:
                    time.sleep(wait_time)
            except Exception as e:
                print(f"Error calling AI platform: {str(e)}")
                self.current_platform_index = (self.current_platform_index + 1) % len(
                    self.ai_platforms
                )

        raise Exception("Max retries reached. Unable to call any AI platform.")

    def _estimate_tokens(self, text: str) -> int:
        # A simple estimation: 1 token ≈ 4 characters
        return len(text) // 4

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
