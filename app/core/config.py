import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "500"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "20.0"))
    REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "25.0"))


settings = Settings()
