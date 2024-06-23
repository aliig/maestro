from typing import Any, Dict

import yaml


class ConfigValidationError(Exception):
    pass


class ConfigManager:
    def __init__(self, config_file: str):
        with open(config_file, "r") as f:
            self.config = yaml.safe_load(f)
        self.validate_config()

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

    def get_github_token(self) -> str:
        return self.config["github_token"]

    def get_ai_keys(self) -> Dict[str, str]:
        return self.config["ai_keys"]

    def get_ai_platforms(self) -> Dict[str, Dict[str, Any]]:
        return self.config["ai_platforms"]

    def get_review_settings(self) -> Dict[str, Any]:
        return self.config.get("review_settings", {})

    def get_value(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
