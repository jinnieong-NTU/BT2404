"""Application configuration and environment variables."""

import os
from pathlib import Path


def _load_env():
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass


_load_env()


class Settings:
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    PORT: int = int(os.environ.get("PORT", "8080"))
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    FACULTY_SECRET_TOKEN: str = os.environ.get(
        "FACULTY_SECRET_TOKEN", "faculty_super_secret_token_bt2404"
    )
    SETTINGS_STORAGE_BACKEND: str = os.environ.get(
        "SETTINGS_STORAGE_BACKEND", "in_memory"
    )


settings = Settings()

