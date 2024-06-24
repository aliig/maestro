from typing import Any, Dict, List
import yaml
import os
from logger import logger

class ConfigValidationError(Exception):
    pass

class ConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()
        self.validate_config()

    def load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_file, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_file}")
            raise ConfigValidationError(f"Config file not found: {self.config_file}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML in config file: {str(e)}")
            raise ConfigValidationError(f"Error parsing YAML in config file: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error loading config file: {str(e)}")
            raise ConfigValidationError(f"Unexpected error loading config file: {str(e)}")

    def validate_config(self):
        try:
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
        except ConfigValidationError as e:
            logger.error(f"Config validation error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during config validation: {str(e)}")
            raise ConfigValidationError(f"Unexpected error during config validation: {str(e)}")

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
        try:
            return self.config.get(key, default)
        except Exception as e:
            logger.error(f"Error getting value for key '{key}': {str(e)}")
            return default

    def update_config(self, key: str, value: Any):
        try:
            self.config[key] = value
            self.save_config()
        except Exception as e:
            logger.error(f"Error updating config for key '{key}': {str(e)}")
            raise ConfigValidationError(f"Error updating config for key '{key}': {str(e)}")

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Error saving config file: {str(e)}")
            raise ConfigValidationError(f"Error saving config file: {str(e)}")

    @staticmethod
    def get_env_variable(var_name: str) -> str:
        try:
            value = os.environ.get(var_name)
            if not value:
                raise ConfigValidationError(f"Environment variable {var_name} is not set")
            return value
        except Exception as e:
            logger.error(f"Error getting environment variable '{var_name}': {str(e)}")
            raise ConfigValidationError(f"Error getting environment variable '{var_name}': {str(e)}")

    def load_env_variables(self):
        try:
            self.config["github_token"] = self.get_env_variable("GITHUB_TOKEN")
            for platform in self.config["ai_platforms"]:
                if platform["provider"] == "anthropic":
                    platform["keys"] = self.get_env_variable("ANTHROPIC_API_KEY").split(",")
                elif platform["provider"] == "openai":
                    platform["keys"] = self.get_env_variable("OPENAI_API_KEY").split(",")
        except Exception as e:
            logger.error(f"Error loading environment variables: {str(e)}")
            raise ConfigValidationError(f"Error loading environment variables: {str(e)}")
