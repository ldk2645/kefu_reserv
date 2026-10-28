import re


def redact(text: str) -> str:
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", text)
    text = re.sub(r"(?<!\d)\d{15,18}[\dXx]?(?!\d)", "[长编号已脱敏]", text)
    text = re.sub(r"((?:订单|运单|快递)(?:编号|号码|号)?\s*[:：]?\s*)[A-Za-z0-9_-]{5,}", r"\1[编号已脱敏]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", text)
    text = re.sub(r"((?:收件人|联系人|姓名|买家姓名)\s*[:：]?\s*)[^\s,，。;；\n]{2,15}", r"\1[姓名已脱敏]", text)
    text = re.sub(r"((?:收货地址|收件地址|地址)\s*[:：]?\s*)[^\n;；]+", r"\1[地址已脱敏]", text)
    text = re.sub(r"[\u4e00-\u9fff]{2,}(?:省|自治区|市)[^\n，。；;]{2,80}(?:号|室|楼|单元)[^\n，。；;]{0,15}", "[地址已脱敏]", text)
    return text


def redact_tree(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_tree(x) for x in value]
    if isinstance(value, dict):
        return {key: redact_tree(val) for key, val in value.items()}
    return value
