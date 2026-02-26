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

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-placeholder")
    AI_MODEL = os.getenv("AI_MODEL", "claude-opus-4-20250514")

    # Server
    HOST = os.getenv("IEYES_HOST", "0.0.0.0")
    PORT = int(os.getenv("IEYES_PORT", "8000"))

    # Review settings
    MAX_DIFF_SIZE = int(os.getenv("MAX_DIFF_SIZE", "50000"))  # chars
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8192"))

    @classmethod
    def validate(cls):
        errors = []
        if not cls.GITLAB_TOKEN:
            errors.append("GITLAB_TOKEN is required")
        if cls.ANTHROPIC_API_KEY == "sk-ant-placeholder":
            errors.append("ANTHROPIC_API_KEY is required (set it in .env)")
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
