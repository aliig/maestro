from typing import Any, Dict, List

import yaml


class ConfigValidationError(Exception):
    pass


class ConfigManager:
    def __init__(self, config_file):
        with open(config_file, "r") as f:
            self.config = yaml.safe_load(f)
        self.validate_config()

    def validate_config(self):
        required_keys = ["github_token", "ai_platforms"]
        for key in required_keys:
            if key not in self.config:
                raise ConfigValidationError(f"Missing required key in config: {key}")

        if not isinstance(self.config["ai_platforms"], list):
            raise ConfigValidationError("'ai_platforms' must be a list")

        for platform in self.config["ai_platforms"]:
            required_platform_keys = ["provider", "model", "keys"]
            for key in required_platform_keys:
                if key not in platform:
                    raise ConfigValidationError(
                        f"Missing required key in platform config: {key}"
                    )

            if not isinstance(platform["keys"], list):
                raise ConfigValidationError(
                    f"'keys' for {platform['provider']} must be a list"
                )

            if len(platform["keys"]) == 0:
                raise ConfigValidationError(
                    f"At least one key must be provided for {platform['provider']}"
                )

    def get_github_token(self) -> str:
        return self.config["github_token"]

    def get_ai_platforms(self) -> List[Dict[str, Any]]:
        return self.config["ai_platforms"]

    def get_review_settings(self, depth: str) -> Dict[str, Any]:
        review_settings = self.config.get("review_settings", {})
        depth_settings = review_settings.get("depth", {}).get(depth, {})
        depth_settings["token_budget"] = review_settings.get("token_budget", 100000)
        return depth_settings

    def get_value(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
