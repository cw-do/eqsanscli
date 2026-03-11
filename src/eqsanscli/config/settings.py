"""Application settings — loads from .env, config.yaml, and runtime overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "google/gemini-3-flash-preview"
FALLBACK_MODEL = "openai/gpt-5-mini"


@dataclass
class LLMSettings:
    """LLM configuration for OpenRouter."""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    fallback_model: str = FALLBACK_MODEL
    base_url: str = "https://openrouter.ai/api/v1"

    @property
    def is_configured(self) -> bool:
        """Whether an API key is available."""
        return bool(self.api_key)


@dataclass
class AppSettings:
    """Top-level application settings."""

    llm: LLMSettings = field(default_factory=LLMSettings)
    output_dir: str = "./output/"
    default_ipts: int = 0

    @classmethod
    def load(cls) -> AppSettings:
        """Load settings from .env file and environment variables."""
        try:
            from dotenv import load_dotenv

            # Try multiple .env locations in order of priority
            env_locations = [
                Path.cwd() / ".env",  # Current directory (user override)
                Path(__file__).resolve().parent.parent.parent.parent / ".env",  # Script directory
                Path.home() / ".eqsanscli" / ".env",  # User's personal config
            ]

            for env_path in env_locations:
                if env_path.is_file():
                    load_dotenv(env_path)
                    break
        except ImportError:
            pass  # python-dotenv not installed — use env vars directly

        settings = cls()
        settings.llm = LLMSettings(
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
            fallback_model=os.getenv("OPENROUTER_FALLBACK_MODEL", FALLBACK_MODEL),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )
        settings.output_dir = os.getenv("EQSANS_OUTPUT_DIR", "./output/")
        ipts_str = os.getenv("EQSANS_DEFAULT_IPTS", "0")
        try:
            settings.default_ipts = int(ipts_str)
        except ValueError:
            settings.default_ipts = 0

        return settings
