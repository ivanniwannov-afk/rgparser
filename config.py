"""Configuration loader for Telegram Lead Monitoring System."""

import json
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


class Config:
    """Configuration manager for the system."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self._data: dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        
        self._validate()
    
    def _validate(self) -> None:
        """Validate required configuration fields."""
        required_fields = [
            "trigger_words",
            "llm_provider",
            "join_delay_min",
            "join_delay_max",
            "daily_join_limit",
            "llm_max_concurrent",
            "llm_timeout",
            "llm_max_retries",
            "health_check_interval",
            "spam_cache_update_interval",
            "max_spam_examples"
        ]
        
        missing_fields = [field for field in required_fields if field not in self._data]
        if missing_fields:
            raise ConfigError(f"Missing required configuration fields: {', '.join(missing_fields)}")
        
        # Validate types and ranges
        if not isinstance(self._data["trigger_words"], list):
            raise ConfigError("trigger_words must be a list")
        
        if self._data["llm_provider"] not in ["claude", "openai", "openrouter"]:
            raise ConfigError("llm_provider must be 'claude', 'openai', or 'openrouter'")
        
        if not (60 <= self._data["join_delay_min"] <= 3600):
            raise ConfigError("join_delay_min must be between 60 and 3600 seconds")
        
        if not (60 <= self._data["join_delay_max"] <= 3600):
            raise ConfigError("join_delay_max must be between 60 and 3600 seconds")
        
        if self._data["join_delay_min"] > self._data["join_delay_max"]:
            raise ConfigError("join_delay_min must be less than or equal to join_delay_max")
        
        if not (1 <= self._data["daily_join_limit"] <= 50):
            raise ConfigError("daily_join_limit must be between 1 and 50")
        
        if self._data["llm_max_concurrent"] < 1:
            raise ConfigError("llm_max_concurrent must be at least 1")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self._data.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        """Get configuration value by key using dict-like syntax."""
        return self._data[key]
    
    def reload(self) -> None:
        """Reload configuration from file (hot reload)."""
        self.load()


# Global config instance
config = Config()
