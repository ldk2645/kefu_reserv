from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    ai_enabled: bool = False
    ai_base_url: str = ""
    ai_api_key: str = field(default="", repr=False)
    ai_model: str = ""
    ai_timeout_seconds: float = 25
    data_dir: Path = ROOT / "data"
    demo_mode: bool = True

    @property
    def online_ready(self):
        return bool(self.ai_enabled and self.ai_base_url and self.ai_api_key and self.ai_model)

    def validate_endpoint(self):
        url = urlsplit(self.ai_base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError("API 地址须为无凭据、无查询参数的 HTTPS 地址（例如 https://服务商/v1）")
        if not 1 <= self.ai_timeout_seconds <= 120:
            raise ValueError("超时须在 1–120 秒之间")


def load_settings(env_path: Path | None = None) -> Settings:
    load_dotenv(env_path or ROOT / ".env", override=False)
    try:
        timeout = max(1, min(120, float(os.getenv("AI_TIMEOUT_SECONDS", "25"))))
    except ValueError:
        timeout = 25
    return Settings(
        ai_enabled=os.getenv("AI_ENABLED", "false").lower() == "true",
        ai_base_url=os.getenv("AI_BASE_URL", "").strip().rstrip("/"),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_model=os.getenv("AI_MODEL", ""),
        ai_timeout_seconds=timeout,
        data_dir=Path(os.getenv("APP_DATA_DIR") or ROOT / "data").resolve(),
    )


def load_yaml(name: str):
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))
