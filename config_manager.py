import os
from typing import Any, Dict

import yaml


class ConfigValidationError(Exception):
    pass


class ConfigManager:
    def __init__(self, config_file):
        with open(config_file, "r") as f:
            self.config = yaml.safe_load(f)

        # Load keys from keys.yml if it exists, otherwise use environment variables
        keys_file = "keys.yml"
        if os.path.exists(keys_file):
            with open(keys_file, "r") as f:
                self.keys = yaml.safe_load(f)
        else:
            self.keys = {
                "github_token": os.environ.get("GITHUB_TOKEN"),
                "ai_keys": {
                    "anthropic": os.environ.get("ANTHROPIC_API_KEY", "").split(","),
                    "openai": os.environ.get("OPENAI_API_KEY", "").split(","),
                },
            }

    def validate_config(self):
        required_keys = ["github_token", "ai_keys", "ai_platforms"]
        for key in required_keys:
            if key not in self.config:
                raise ConfigValidationError(f"Missing required key in config: {key}")

        if not isinstance(self.config["ai_keys"], dict):
            raise ConfigValidationError("'ai_keys' must be a dictionary")

        if not isinstance(self.config["ai_platforms"], dict):
            raise ConfigValidationError("'ai_platforms' must be a dictionary")

        for platform, config in self.config["ai_platforms"].items():
            required_platform_keys = ["provider", "model", "max_tokens"]
            for key in required_platform_keys:
                if key not in config:
                    raise ConfigValidationError(
                        f"Missing required key in platform config for {platform}: {key}"
                    )

    def get_github_token(self):
        return self.keys["github_token"]

    def get_ai_keys(self):
        return self.keys["ai_keys"]

    def get_ai_platforms(self) -> Dict[str, Dict[str, Any]]:
        return self.config["ai_platforms"]

    def get_review_settings(self, depth):
        review_settings = self.config["review_settings"]
        depth_settings = review_settings["depth"][depth]
        depth_settings["token_budget"] = review_settings["token_budget"]
        return depth_settings

    def get_value(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
