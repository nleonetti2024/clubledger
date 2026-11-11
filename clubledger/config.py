"""Configuration, read from environment variables (and an optional .env file).

Nothing secret is hard-coded for production use. The defaults below exist only
so the prototype runs out of the box for a local demo; the app logs a warning
when they are in use.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"
DEV_TREASURER_PIN = "4010"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file without overriding real env vars.

    A tiny loader so the project needs no extra dependency for this.
    """
    path = path or PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Config:
    """Settings for the running app. Construct after load_dotenv()."""

    def __init__(self) -> None:
        env = os.environ.get
        self.SECRET_KEY = env("CLUBLEDGER_SECRET_KEY", DEV_SECRET_KEY)
        self.TREASURER_PIN = env("CLUBLEDGER_TREASURER_PIN", DEV_TREASURER_PIN)
        self.DATABASE = env(
            "CLUBLEDGER_DATABASE", str(PROJECT_ROOT / "instance" / "clubledger.sqlite3")
        )
        self.POLICY_PATH = env(
            "CLUBLEDGER_POLICY", str(PROJECT_ROOT / "policy" / "club_policy.yaml")
        )
        # auto = use Anthropic if a key is set, otherwise the offline reader
        self.EXTRACTOR = env("CLUBLEDGER_EXTRACTOR", "auto").lower()
        self.ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
        self.ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-5-5")
        self.AI_TIMEOUT_SECONDS = float(env("CLUBLEDGER_AI_TIMEOUT", "20"))
        self.MAX_RECEIPT_CHARS = int(env("CLUBLEDGER_MAX_RECEIPT_CHARS", "5000"))
        # Optional fixed "today" (YYYY-MM-DD) so demos with sample receipts are repeatable.
        self.AS_OF = env("CLUBLEDGER_AS_OF", "")
        self.MAX_CONTENT_LENGTH = 64 * 1024  # uploads larger than 64 KB are refused
        self.TESTING = False

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if k.isupper()}
