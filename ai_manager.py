import json
import re
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from logger import logger
from utils import clean_diff


class AIInterface(ABC):
    @abstractmethod
    def call_ai(self, prompt: str) -> str:
        pass

    @abstractmethod
    def get_rate_limit_reset_time(self, error) -> float:
        pass


class AnthropicAI(AIInterface):
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    @retry(
        retry=retry_if_exception_type((anthropic.APIError, anthropic.APIConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    def call_ai(self, prompt: str) -> str:
        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            return response.content[0].text
        except anthropic.RateLimitError as e:
            logger.warning(f"Rate limit reached for Anthropic AI. Retrying in {self.get_rate_limit_reset_time(e)} seconds.")
            raise
        except (anthropic.APIError, anthropic.APIConnectionError) as e:
            logger.error(f"Error calling Anthropic AI: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Anthropic AI: {str(e)}")
            raise

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
    def __init__(self, api_key: str, model: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    @retry(
        retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    def call_ai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except openai.RateLimitError as e:
            logger.warning(f"Rate limit reached for OpenAI GPT. Retrying in {self.get_rate_limit_reset_time(e)} seconds.")
            raise
        except (openai.APIError, openai.APIConnectionError) as e:
            logger.error(f"Error calling OpenAI GPT: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling OpenAI GPT: {str(e)}")
            raise

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
        self.max_retries = self.config_manager.get_value("max_retries", 3)

    def _initialize_ai_platforms(self) -> List[AIInterface]:
        ai_platforms = []
        platforms = self.config_manager.get_ai_platforms()

        for platform in platforms:
            provider = platform["provider"]
            keys = platform["keys"]
            model = platform["model"]
            for key in keys:
                if provider == "anthropic":
                    ai_platforms.append(AnthropicAI(key, model))
                elif provider == "openai":
                    ai_platforms.append(OpenAIGPT(key, model))
                else:
                    raise ValueError(f"Invalid AI provider: {provider}")

        return ai_platforms

    def call_ai(self, prompt: str) -> str:
        for _ in range(len(self.ai_platforms)):
            current_platform = self.platform_queue[0]
            try:
                result = current_platform.call_ai(prompt)
                return result
            except (anthropic.RateLimitError, openai.RateLimitError) as e:
                wait_time = current_platform.get_rate_limit_reset_time(e)
                logger.warning(f"Rate limit reached for {current_platform.__class__.__name__}. Waiting {wait_time} seconds.")
                time.sleep(wait_time)
                self.platform_queue.rotate(-1)  # Move the current platform to the end
            except Exception as e:
                logger.error(f"Error using {current_platform.__class__.__name__}: {str(e)}")
                self.platform_queue.rotate(-1)  # Move the current platform to the end

        raise Exception("All AI platforms exhausted. Unable to complete the request.")

    def analyze_changes_and_update_readme(
        self,
        original_structure,
        new_structure,
        original_readme,
        changes_summary,
        prompt_manager,
    ):
        cleaned_changes = {}
        for file, content in new_structure.items():
            if file in original_structure:
                cleaned_changes[file] = clean_diff(original_structure[file], content)
            else:
                cleaned_changes[file] = f"New file: {file}\n{content}"

        prompt = prompt_manager.get_readme_update_prompt(
            original_structure.keys(),
            new_structure.keys(),
            cleaned_changes,
            changes_summary,
            original_readme,
        )

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
