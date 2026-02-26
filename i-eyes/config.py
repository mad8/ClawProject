"""
I-Eyes Configuration
Load settings from environment variables.
"""

import os


class Config:
    # GitLab
    GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.com")
    GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")  # Personal Access Token or Bot Token
    GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")

    # AI Provider (OpenAI-compatible API)
    AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1")
    AI_API_KEY = os.getenv("AI_API_KEY")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o")

    # Server
    HOST = os.getenv("IEYES_HOST", "0.0.0.0")
    PORT = int(os.getenv("IEYES_PORT", "8000"))

    # Review settings
    MAX_DIFF_SIZE = int(os.getenv("MAX_DIFF_SIZE", "50000"))  # chars
    REVIEW_LANGUAGE = os.getenv("REVIEW_LANGUAGE", "fr")  # fr or en

    @classmethod
    def validate(cls):
        errors = []
        if not cls.GITLAB_TOKEN:
            errors.append("GITLAB_TOKEN is required")
        if not cls.AI_API_KEY:
            errors.append("AI_API_KEY is required")
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
