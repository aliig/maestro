import time
from typing import List, Dict, Any
from abc import ABC, abstractmethod
import anthropic
import openai
from datetime import datetime, timezone

class AIInterface(ABC):
    @abstractmethod
    def call_ai(self, prompt: str) -> str:
        pass

    @abstractmethod
    def get_rate_limit_reset_time(self, error) -> float:
        pass

class AnthropicAI(AIInterface):
    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def call_ai(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    def get_rate_limit_reset_time(self, error) -> float:
        if isinstance(error, anthropic.RateLimitError):
            headers = error.response.headers
            reset_time = headers.get('anthropic-ratelimit-reset')
            if reset_time:
                return max((datetime.fromisoformat(reset_time.replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds(), 0)
        return 60  # Default to 60 seconds if we can't determine the actual reset time

class OpenAIGPT(AIInterface):
    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def call_ai(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.max_tokens
        )
        return response.choices[0].message.content

    def get_rate_limit_reset_time(self, error) -> float:
        if isinstance(error, openai.RateLimitError):
            headers = error.response.headers
            reset_time = headers.get('x-ratelimit-reset-requests')
            if reset_time:
                return max(float(reset_time) - time.time(), 0)
        return 60  # Default to 60 seconds if we can't determine the actual reset time

class AIManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.ai_platforms = self._initialize_ai_platforms()
        self.current_platform_index = 0
        self.max_retries = self.config_manager.get_value('max_retries', 3)

    def _initialize_ai_platforms(self) -> List[AIInterface]:
        ai_platforms = []
        ai_keys = self.config_manager.get_ai_keys()
        platforms_config = self.config_manager.get_ai_platforms()

        for platform, config in platforms_config.items():
            provider = config['provider']
            api_keys = ai_keys[provider]
            model = config['model']
            max_tokens = config['max_tokens']

            if not isinstance(api_keys, list):
                api_keys = [api_keys]

            for api_key in api_keys:
                if provider == 'anthropic':
                    ai_platforms.append(AnthropicAI(api_key, model, max_tokens))
                elif provider == 'openai':
                    ai_platforms.append(OpenAIGPT(api_key, model, max_tokens))

        return ai_platforms

    def call_ai(self, prompt: str) -> str:
        start_index = self.current_platform_index
        for _ in range(len(self.ai_platforms)):
            try:
                result = self.ai_platforms[self.current_platform_index].call_ai(prompt)
                return result
            except (anthropic.RateLimitError, openai.RateLimitError) as e:
                wait_time = self.ai_platforms[self.current_platform_index].get_rate_limit_reset_time(e)
                print(f"Rate limit reached for API key {self.current_platform_index}. Waiting time: {wait_time:.2f} seconds.")

                # Move to the next API key
                self.current_platform_index = (self.current_platform_index + 1) % len(self.ai_platforms)

                # If we've tried all keys and are back to the start, wait for the shortest reset time
                if self.current_platform_index == start_index:
                    time.sleep(wait_time)
            except Exception as e:
                print(f"Error calling AI platform: {str(e)}")
                self.current_platform_index = (self.current_platform_index + 1) % len(self.ai_platforms)

        raise Exception("Max retries reached. Unable to call any AI platform.")