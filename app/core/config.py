import os
from pathlib import Path

from dotenv import load_dotenv

# Always load .env from project root (parent of app/)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "") or os.getenv(
        "GOOGLE_API_KEY", ""
    )

    MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "1024"))
    POLISH_MAX_TOKENS: int = int(os.getenv("POLISH_MAX_TOKENS", "400"))
    THINKING_BUDGET: int = int(os.getenv("THINKING_BUDGET", "0"))

    ENABLE_LLM_POLISH: bool = os.getenv("ENABLE_LLM_POLISH", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "4.0"))
    REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "6.0"))


settings = Settings()
