"""Fail-closed boundaries shared by navigation, normalization and import."""
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "kbs_import"
ENTRY = "https://kbs.be.xiaomi.com/home/"
AUTH_KEY = re.compile(r"token|cookie|session|password|passwd|secret|credential|authorization|signature|^sign$|^code$|^ticket$|^auth$|^sid$|^jwt$|^cuserid$|^userid$", re.I)


class CollectorError(Exception):
    """Only fixed, non-sensitive error codes may cross the UI/log boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def safe_url(value, *, fixture=False):
    """Keep accepted URLs byte-for-byte; reject sensitive URLs, never sanitize tokens."""
    try:
        if not value or re.search(r"[\s<>\x00-\x1f\\]", value):
            return False
        url = urlsplit(value)
        if url.username or url.password or not url.hostname:
            return False
        if fixture and url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}:
            pass
        elif url.scheme != "https" or url.port not in (None, 443):
            return False
        host = url.hostname.lower()
        if host.startswith(("account.", "login.", "passport.")):
            return False
        if re.search(r"(?:^|/)(?:login|servicelogin|oauth|authorize|logout)(?:/|$)", url.path, re.I):
            return False
        parts = [url.query, url.fragment.partition("?")[2], url.fragment]
        for part in parts:
            if any(AUTH_KEY.search(unquote(key)) for key, _ in parse_qsl(part)):
                return False
        if re.search(r"(?:bearer|eyJ[a-zA-Z0-9_-]{15,})", unquote(value), re.I):
            return False
        return True
    except (ValueError, TypeError):
        return False


def source_allowed(value, *, fixture=False):
    if not safe_url(value, fixture=fixture):
        return False
    host = urlsplit(value).hostname
    return host == "kbs.be.xiaomi.com" or (fixture and host in {"127.0.0.1", "localhost"})


def exact_model_in(model, text):
    # A1 must not match A10, A1-Pro, or A1/2. Never use fuzzy model matching.
    return bool(model and re.search(r"(?<![\w./-])" + re.escape(model) + r"(?![\w./-])", text))


def local_path(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(DATA.resolve()):
        raise CollectorError("LOCAL_PATH_REQUIRED")
    return resolved
