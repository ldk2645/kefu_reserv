import ipaddress
import re
from urllib.parse import urlsplit
from app.repositories.catalog import Catalog


def valid_public_url(value, allow_demo=False):
    if re.search(r"[\s<>\x00-\x1f]", value):
        return False
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if url.scheme != "https" or not host or url.username or url.password:
            return False
        if url.port not in (None, 443):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        if "." not in host or host.endswith((".local", ".localhost", ".test", ".invalid")):
            return False
        if not allow_demo and any(host == h or host.endswith("."+h) for h in ("example.com", "example.org", "example.net")):
            return False
        return True
    except ValueError:
        return False


def video_intent(question):
    q = question.lower()
    for tag, words in [("cleaning", ["清洁", "清洗"]), ("reset", ["复位", "重置"]),
                       ("installation", ["安装"]), ("pairing", ["蓝牙", "配对"]),
                       ("wifi_setup", ["wifi", "wi-fi", "配网", "联网", "网络"])]:
        if any(word in q for word in words):
            return tag
    if "连接" in q and "耳机" in q:
        return "pairing"
    if "连接" in q and "摄像头" in q:
        return "wifi_setup"
    return "other"


def eligible(video, product_id, intent):
    return (video.product_id == product_id and video.verified_status == "approved"
            and not video.is_demo and video.customer_shareable and video.link_status == "valid"
            and bool(video.verified_by and video.verified_at and video.last_checked_at)
            and bool(video.official_source_name) and valid_public_url(video.official_source_url)
            and intent in video.intent_tags and valid_public_url(video.url))


def find_videos(db, product_id, question):
    product = Catalog(db).product(product_id)
    if not product or product["is_demo"]:
        return []
    return [v for v in Catalog(db).videos() if eligible(v, product_id, video_intent(question))][:1]
