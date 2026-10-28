import re
from app.models import RiskAssessment
from app.settings import load_yaml


def assess(question, product, hits, context=""):
    text = question + "\n" + context
    config = load_yaml("rules.yaml")["risk"]
    safety = config["R3_safety_keywords"] + ["鼓了", "发烫", "过热", "着火", "电池爆", "冒火", "漏电"]
    commercial = config["R2_commercial_keywords"] + ["赔我", "赔付", "补偿", "能退", "退货", "多久到", "保修", "质保", "退吗"]
    if any(word in text for word in safety):
        return RiskAssessment(intent="safety", risk_level="R3", reasons=["涉及设备安全，需人工优先处理"])
    if any(word in text for word in commercial) or re.search(r"赔\s*\d+", text):
        intent = "complaint" if "投诉" in text else "logistics" if any(w in text for w in ["到货", "多久到", "物流"]) else "refund"
        return RiskAssessment(intent=intent, risk_level="R2", reasons=["涉及经营承诺，需核对当前有效 SOP"])
    intent = "how_to_use" if any(w in question.lower() for w in ["怎么", "连接", "wifi", "配对", "安装", "教程"]) else "troubleshooting"
    if not product:
        return RiskAssessment(intent=intent, risk_level="R1", reasons=["准确型号未确认"], missing_information=["准确型号"])
    if not hits:
        return RiskAssessment(intent=intent, risk_level="R1", reasons=["已审核资料未覆盖问题"], missing_information=["相关说明书或具体症状"])
    return RiskAssessment(intent=intent, risk_level="R0", reasons=["有同型号资料，仍需人工复核适用性"])
