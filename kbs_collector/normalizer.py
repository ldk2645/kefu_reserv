from datetime import datetime, timezone
import hashlib
import json
import re

from .extractor import Capture
from .policy import CollectorError, safe_url, source_allowed, exact_model_in


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def block_text(block):
    if block["kind"] == "table":
        return "\n".join(" | ".join(c["text"] for c in row) for row in block["rows"])
    if block["kind"] == "step":
        return "  " * block.get("depth",0) + (str(block["number"])+". " if block.get("number") is not None else "- ") + block.get("text", "")
    return block.get("text", "")


def normalize(raw, product, *, fixture=False):
    if not source_allowed(raw["source_url"], fixture=fixture) or not safe_url(raw["frame_url"], fixture=fixture):
        raise CollectorError("UNSAFE_SOURCE_URL")
    if raw["characters"] > 1_000_000 or len(raw["blocks"]) > 10000:
        raise CollectorError("CONTENT_TOO_LARGE")
    if not raw["blocks"] or not any(block_text(b).strip() for b in raw["blocks"]):
        raise CollectorError("EMPTY_CONTENT")
    issues, blocks, headings = [], [], []
    if raw.get("withheld_links"):
        issues.append("LINK_WITHHELD_UNSAFE")
    for item in raw["blocks"]:
        block = dict(item)
        if block["kind"] == "heading":
            level = block["level"]
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, block["text"]))
        block["section"] = [h[1] for h in headings]
        blocks.append(block)
    body = "\n".join(block_text(b) for b in blocks)
    if any(b.get('audience') == 'internal' for b in blocks):
        issues.append('INTERNAL_NOTES_OPERATOR_ONLY')
    evidence = product.model_evidence
    if (not product.model or not evidence or evidence not in body or
            not exact_model_in(product.model, evidence)):
        issues.append("MODEL_UNCONFIRMED")
    if re.search(r"忽略.{0,12}(?:指令|规则)|ignore.{0,30}instructions|system\s*prompt", body, re.I):
        issues.append("UNTRUSTED_INSTRUCTION_TEXT")
    links, videos, seen = [], [], set()
    for candidate in raw["links"]:
        url = candidate["url"]
        if not safe_url(url, fixture=fixture):
            issues.append("LINK_WITHHELD_UNSAFE")
            continue
        if url in seen:
            continue
        seen.add(url)
        # URLs and parameters are retained exactly as provided by the DOM.
        link = {k:candidate[k] for k in ("title", "url", "context")}
        link['audience'] = candidate.get('audience', 'external')
        raw_href = candidate.get("raw_href", "")
        link["raw_href"] = raw_href if not raw_href.startswith(("javascript:", "data:")) else ""
        link["kind"] = "reference"
        if candidate.get('media_type') == 'video' or re.search(r"视频|video|教程播放", link["title"], re.I):
            link["kind"] = "video"
            videos.append(dict(link, applicable_model=product.model if "MODEL_UNCONFIRMED" not in issues else "",
                purpose=link["context"], status="pending_review", official_verified=False,
                customer_shareable=False, link_status="unknown", page_confirmed=True))
        elif re.search(r"说明书|手册|manual|\.pdf(?:[?#]|$)|\.docx?(?:[?#]|$)", link["title"]+" "+url, re.I):
            link["kind"] = "manual"
        links.append(link)
    faq, question = [], None
    for block in blocks:
        if block.get('audience') == 'internal':
            continue
        text = block_text(block)
        if block["kind"] == "question" or re.match(r"^(?:Q\s*[:：]|问\s*[:：])", text, re.I):
            question = {"question":text, "answer":[], "section":block["section"], "status":"pending_review"}
            faq.append(question)
        elif block["kind"] in {"heading", "field"}:
            question = None
        elif question:
            question["answer"].append(text)
    if any(not f["answer"] for f in faq):
        issues.append("FAQ_INCOMPLETE")
    if not faq:
        issues.append("FAQ_NOT_STRUCTURED_VERIFY_MANUALLY")
    displayed_times = list(raw["displayed_times"])
    for block in blocks:
        text = block_text(block)
        if len(text) <= 150 and re.search(r"(?:更新|修订|发布时间).{0,20}\d{4}[-年/.]\d{1,2}",text):
            displayed_times.append(text)
    clean = {**raw, "blocks":blocks, "links":links, "product":product,"displayed_times":list(dict.fromkeys(displayed_times)),
             "captured_at":now(), "issues":sorted(set(issues)), "faq":faq, "videos":videos}
    capture = Capture(**clean)
    content = capture.model_dump(exclude={"id", "content_hash", "captured_at", "issues", "frame_path", "root_selector", "characters"})
    capture.content_hash = digest(content)
    capture.id = digest([capture.source_url, product.brand, product.model, capture.content_hash])
    return capture


def markdown(capture):
    # Local review artifact only; the application never executes Markdown/HTML.
    lines = ["# " + capture.title, "", "状态：pending_review；仅供本地人工审核",
             "型号：" + capture.product.model, "来源：" + capture.source_url,
             "采集时间：" + capture.captured_at, ""]
    for block in capture.blocks:
        if block["kind"] == "heading":
            lines.append("#" * block["level"] + " " + block["text"])
        elif block.get('audience') == 'internal':
            lines.append('【内部备注，仅供操作员审核】' + block_text(block))
        else:
            lines.append(block_text(block))
        lines.append("")
    lines.append("## 页面原始链接（未经官方性、分享权限或有效性审核）")
    lines.extend(link["title"] + "\n" + link["url"] for link in capture.links)
    return "\n".join(lines)
