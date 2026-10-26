import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
KEY_FILES = [ROOT_DIR / ".env", Path.home() / "Documents/github/observatory-site/.env"]


def key_from_files(paths=None) -> str:
    for p in KEY_FILES if paths is None else paths:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    return ""


class Settings(BaseSettings):
    max_body_bytes: int = 6 * 1024 * 1024
    database_url: str = f"sqlite:///{ROOT_DIR / 'quickviz.db'}"
    public_url: str = "http://localhost:8011"
    production: bool = False
    session_hours: int = 720
    google_client_id: str = ""
    google_client_secret: str = ""
    admin_email: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai"
    openrouter_referer: str = "https://quickviz.franri.dev"
    openrouter_title: str = "QuickViz"

    usd_per_credit: float = 0.001
    credits_anon_day: int = 100
    credits_user_day: int = 1000
    call_credits: int = 5
    global_day_usd: float = 3.0
    fallback_cost_usd: float = 0.01

    model_config = SettingsConfigDict(
        env_file=os.environ.get("QUICKVIZ_ENV_FILE") or ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def public_origin(self) -> str:
        parts = urlsplit(self.public_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def google_on(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def admin(self) -> str:
        return self.admin_email.strip().lower()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.openrouter_api_key and not os.environ.get("QUICKVIZ_ENV_FILE"):
        s.openrouter_api_key = key_from_files()
    return s
