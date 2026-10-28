from dataclasses import dataclass
import re

from app.models import Draft, ModelReply
from app.repositories.catalog import Catalog
from app.services.llm_client import LLMClient, ProviderError
from app.services.redaction import redact_tree
from app.services.retrieval import retrieve, INJECTION, tokens
from app.services.risk import assess
from app.services.video_links import find_videos, eligible, video_intent
from app.settings import load_yaml

DEMO_PREFIX = "【虚构演示，请勿发送真实客户】\n"
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\u3000-\u303f\uff00-\uffef]+", re.I)
PROMISE = re.compile(r"(?:保证|承诺|一定|肯定|马上|立即|直接|免费|无条件).{0,15}(?:退|赔|补发|到货|到账|送达|运费)|"
                     r"(?:给您|给你|帮您|帮你|同意|批准).{0,8}(?:退款|赔偿|赔付|补偿)|(?:赔|退)\s*\d+|"
                     r"\d+\s*(?:小时|天|日).{0,4}(?:内|后|就)?.{0,4}(?:到货|送达|退款|到账)")


@dataclass
class Evidence:
    product: dict | None
    hits: list
    policies: list
    videos: list
    risk: object
    is_demo: bool


def prepare(db, context, demo_mode=False):
    if not context.confirmed_by_user or not context.latest_customer_message.strip():
        raise ValueError("请先人工确认最新买家问题")
    product = Catalog(db).product(context.product_id) if context.product_id else None
    if product and product["is_demo"] and not demo_mode:
        raise ValueError("真实资料模式不能使用演示商品，请选择真实型号")
    if product and context.sku != product["sku"]:
        raise ValueError("SKU 映射已改变，请重新选择商品")
    hits = retrieve(db, context.product_id, context.latest_customer_message, demo=demo_mode)
    policies = retrieve(db, context.product_id, context.latest_customer_message, policies=True)
    risk = assess(context.latest_customer_message, product, hits, context.conversation_context)
    videos = find_videos(db, context.product_id, context.latest_customer_message) if risk.risk_level < "R2" else []
    return Evidence(product, hits, policies, videos, risk, bool(product and product["is_demo"]))


def build_payload(context, evidence):
    if evidence.is_demo:
        raise ValueError("虚构演示资料不能提交外部模型")
    return redact_tree({
        "confirmed_latest_customer_message": context.latest_customer_message[:1500],
        "confirmed_conversation_context": context.conversation_context[:1800],
        "confirmed_model": evidence.product["model"] if evidence.product else None,
        "verified_knowledge_snippets": [dict(id=h.chunk_id, product_model=evidence.product["model"],
             page=h.page, excerpt=h.excerpt) for h in evidence.hits[:5] if not h.is_demo],
        "valid_shop_policies": [dict(id=h.chunk_id, excerpt=h.excerpt) for h in evidence.policies],
        "approved_video_candidates": [dict(id=v.video_id, title=v.title, intent=v.intent_tags) for v in evidence.videos],
        "programmatic_risk_flags": evidence.risk.model_dump(),
        "response_style": {"max_chinese_chars": 130, "max_steps": 2},
    })


def local_reply(context, evidence):
    risk = evidence.risk
    knowledge_ids, videos = [], []
    if risk.risk_level == "R3":
        text = "您好，请先停止使用；确保安全可行时停止充电，避免挤压、拆卸或接触异常设备。请由人工优先协助处理。"
    elif risk.risk_level == "R2":
        text = "您好，您的诉求我已了解。具体处理方式需由人工结合实际情况和现行规则核实，暂时无法确认金额或时效。麻烦您说明具体问题。"
    elif not evidence.product:
        text = "您好，麻烦您提供设备的准确型号，并说明目前的具体异常，我核对对应资料后再协助您处理。"
    elif not evidence.hits:
        text = "您好，目前资料还不足以确认具体操作。麻烦您说明出现问题时的现象和提示信息，我核实对应型号的资料后再协助您。"
    else:
        hit = evidence.hits[0]
        excerpt = hit.excerpt.strip()
        # Local mode quotes evidence without inventing steps. Ask for confirmation if
        # the only retrieved instruction repeats a step already in the context.
        if "换" in context.conversation_context and "换" in excerpt:
            text = "您好，已了解您尝试过更换配件。麻烦您补充当前的提示或指示灯状态，我再核实后续处理方法。"
        else:
            text = "您好，对应资料记载：\n" + excerpt[:400] + "\n请先核对是否符合您当前的情况。"
            knowledge_ids = [hit.chunk_id]
        videos = [v.video_id for v in evidence.videos[:1]]
    return ModelReply(intent=risk.intent, risk_level=risk.risk_level,
        missing_information=risk.missing_information, customer_reply=text,
        operator_note="本地模板引用；请人工核对原文、适用条件及客户已尝试的步骤。",
        used_knowledge_ids=knowledge_ids, used_video_ids=videos)


def validate_text(text, evidence, allow_urls=True):
    errors = []
    if not text.strip():
        errors.append("回复为空")
    if len(text) > 2000:
        errors.append("回复过长，请精简")
    banned = load_yaml("persona.yaml")["customer_reply_style"]["banned_terms"]
    if any(term.casefold() in text.casefold() for term in banned):
        errors.append("客户回复包含操作员人格词汇")
    urls = URL_PATTERN.findall(text)
    allowed = {v.url for v in evidence.videos} if allow_urls else set()
    if any(url not in allowed for url in urls) or re.search(r"(?:https?:|www\.)", URL_PATTERN.sub("", text), re.I):
        errors.append("回复含未经本次审核的 URL")
    if re.search(r"(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|test|xyz|top)(?:[/\s]|$)|(?:ftp|file)://", URL_PATTERN.sub("", text), re.I):
        errors.append("回复含未经审核的裸域名或链接")
    if INJECTION.search(text):
        errors.append("回复包含指令注入文本")
    if PROMISE.search(text):
        errors.append("回复包含未经授权的经营承诺")
    if re.search(r"(?:我|已|已经).{0,6}(?:查过|查看|查询|查到).{0,6}(?:订单|物流)", text):
        errors.append("不能声称已查询真实订单")
    if re.search(r"视频.{0,12}(?:\d+\s*秒|我看|看过|演示了|说了)", text):
        errors.append("程序未解析视频，不能描述视频内容")
    if evidence.risk.risk_level == "R3":
        if "停止" not in text or "人工" not in text:
            errors.append("安全风险回复必须保留停止使用及人工处理提醒")
        if re.search(r"(?:可以|继续|试着|请您|建议).{0,8}(?:拆开|拆机|短接|刺破|继续充电)", text):
            errors.append("安全风险回复包含危险操作")
        if re.search(r"(?<!停止)(?<!不要)(?<!禁止)(?<!避免)(?<!不应)继续(?:使用|充电)", text):
            errors.append("安全风险下不能建议继续使用或充电")
    body = URL_PATTERN.sub("", text)
    facts = "\n".join(h.excerpt for h in evidence.hits + evidence.policies)
    if any(number not in facts for number in re.findall(r"\d+(?:\.\d+)?\s*(?:秒|分钟|小时|天|元|伏|瓦|毫安|mAh|W|V|Hz|GHz)", body, re.I)):
        errors.append("回复包含没有资料依据的具体数值")
    # Conservative lexical gate for common unsupported specifications and actions.
    # It intentionally rejects some valid paraphrases; human review remains necessary.
    if evidence.risk.risk_level < "R2":
        fact_terms = tokens(facts)
        for clause in re.split(r"[，。！？\n；]", body):
            if re.search(r"麻烦|请提供|说明.{0,8}(?:现象|问题)|是否|什么|核实|准确型号|资料还不足", clause):
                continue
            if re.search(r"支持|兼容|防水|无线充电|双频|长按|复位|重置|拆开|拆机|短接|刺破|点击|打开|选择|插入|拔出", clause):
                terms = tokens(clause)
                if terms and len(terms & fact_terms) / len(terms) < .55:
                    errors.append("操作或功能描述缺少本次资料支持，请核对原文")
                    break
    return errors


def validate_model(reply, evidence):
    allowed_ids = {h.chunk_id for h in evidence.hits + evidence.policies}
    if not set(reply.used_knowledge_ids) <= allowed_ids:
        raise ValueError("模型输出了不存在的知识引用")
    if not set(reply.used_video_ids) <= {v.video_id for v in evidence.videos}:
        raise ValueError("模型输出了未批准的视频引用")
    errors = validate_text(reply.customer_reply, evidence, allow_urls=False)
    if errors:
        raise ValueError("；".join(errors))
    if evidence.hits and not reply.used_knowledge_ids:
        raise ValueError("模型未给出本次资料依据，请人工确认")


def generate(context, evidence, settings, payload=None, client=None, include_video=True):
    reply = local_reply(context, evidence)
    mode = "演示回复（Mock）" if settings.demo_mode else "本地保守草稿（Mock）"
    note = ""
    if settings.online_ready and not evidence.is_demo and evidence.risk.risk_level == "R0":
        if payload is None or payload != build_payload(context, evidence):
            raise ValueError("在线生成前必须确认本次脱敏数据预览")
        try:
            candidate = (client or LLMClient(settings)).generate(payload)
            validate_model(candidate, evidence)
            if candidate.risk_level > evidence.risk.risk_level:
                evidence.risk.risk_level = candidate.risk_level
                reply = local_reply(context, evidence)
                note = "模型提示更高风险，已使用本地保守草稿。"
            else:
                reply, mode = candidate, "AI 回复 · 待人工审核"
        except (ProviderError, ValueError):
            note = "API 失败或输出未通过校验，已回退本地保守草稿；未采用模型原始文本。"
    if evidence.is_demo:
        reply.customer_reply = DEMO_PREFIX + reply.customer_reply
    if include_video and evidence.risk.risk_level < "R2":
        chosen = [v for v in evidence.videos if v.video_id in reply.used_video_ids][:1]
        for video in chosen:
            reply.customer_reply += "\n官方教程：" + video.url
        reply.used_video_ids = [v.video_id for v in chosen]
    else:
        reply.used_video_ids = []
    errors = validate_text(reply.customer_reply, evidence)
    if errors:
        # Even imported, reviewed text can contain harmful/instructional content.
        reply.customer_reply = (DEMO_PREFIX if evidence.is_demo else "") + "您好，当前资料需要进一步人工核实。麻烦您说明具体问题和准确型号，我再协助您确认。"
        reply.used_knowledge_ids = []
        reply.used_video_ids = []
        note += " 引用文本未通过校验，已移除；请查看来源原文。"
    reply.risk_level = max(reply.risk_level, evidence.risk.risk_level)
    reply.operator_note += " " + note
    return Draft(**reply.model_dump(), context_fingerprint=context.fingerprint, mode=mode, is_demo=evidence.is_demo)


def review_copy(db, draft, context, text, reviewed, demo_mode):
    if not reviewed:
        raise ValueError("请勾选已审核当前回复")
    if (not draft or draft.stale or not context.confirmed_by_user
            or draft.context_fingerprint != context.fingerprint):
        raise ValueError("草稿已失效，请确认当前问题并重新生成")
    evidence = prepare(db, context, demo_mode)
    evidence.risk.risk_level = max(evidence.risk.risk_level, draft.risk_level)
    valid_ids = {h.chunk_id for h in evidence.hits + evidence.policies}
    if not set(draft.used_knowledge_ids) <= valid_ids:
        raise ValueError("引用资料已变更或撤回，请重新生成")
    if draft.is_demo and (not demo_mode or not text.startswith(DEMO_PREFIX)):
        raise ValueError("演示回复必须保留演示标记；不能发送真实客户")
    errors = validate_text(text, evidence)
    if errors:
        raise ValueError("；".join(errors))
    return text
