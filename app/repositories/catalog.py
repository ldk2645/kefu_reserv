from datetime import datetime, timezone, date
import json
from uuid import uuid4

from app.models import VideoSuggestion


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Catalog:
    def __init__(self, db):
        self.db = db

    def products(self):
        return self.db.rows("SELECT * FROM products WHERE active=1 ORDER BY is_demo DESC,model,sku")

    def product(self, product_id):
        rows = self.db.rows("SELECT * FROM products WHERE id=? AND active=1", (product_id,))
        return rows[0] if rows else None

    def add_product(self, brand, name, model, sku, aliases="", category="", is_demo=False, product_id=None):
        if not all(str(v).strip() for v in (name, model, sku)):
            raise ValueError("商品名称、准确硬件型号和 SKU 均必填")
        if self.db.rows("SELECT id FROM products WHERE sku=?", (sku.strip(),)):
            raise ValueError("SKU 已存在，请核对型号映射，不能静默覆盖")
        product_id = product_id or uuid4().hex
        with self.db.connect() as conn:
            conn.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,1,?)", (
                product_id, brand.strip(), name.strip(), model.strip(), sku.strip(),
                json.dumps([a.strip() for a in aliases.split(",") if a.strip()], ensure_ascii=False),
                category, int(is_demo), now()))
        return product_id

    def match(self, exact_value):
        value = exact_value.strip().casefold()
        matches = [p for p in self.products() if value in
                   [str(p[k]).casefold() for k in ("model", "sku", "id")]
                   + [a.casefold() for a in json.loads(p["aliases"])]]
        return matches[0] if len(matches) == 1 else None

    def sources(self):
        return self.db.rows("SELECT s.*,p.model,p.sku FROM knowledge_sources s JOIN products p ON p.id=s.product_id ORDER BY imported_at DESC")

    def source_chunks(self, source_id):
        return self.db.rows("SELECT * FROM knowledge_chunks WHERE source_id=? ORDER BY rowid", (source_id,))

    def review_source(self, source_id, status, reviewer):
        if status not in {"approved", "pending", "rejected", "deprecated"} or not reviewer.strip():
            raise ValueError("请选择审核状态并填写审核员别名")
        source = next((s for s in self.sources() if s["id"] == source_id), None)
        if not source:
            raise ValueError("资料不存在")
        if status == "approved":
            if source["is_demo"]:
                raise ValueError("虚构演示资料不能批准为真实事实")
            if not source["provenance"].strip():
                raise ValueError("请先填写可核对的来源")
            if source["kind"] == "shop_policy":
                if not source["effective_at"] or not source["expires_at"]:
                    raise ValueError("SOP 必须有生效和失效日期")
                if not source["effective_at"] <= date.today().isoformat() <= source["expires_at"]:
                    raise ValueError("SOP 不在有效期内")
        with self.db.connect() as conn:
            conn.execute("UPDATE knowledge_sources SET verified_status=?,reviewed_at=?,verified_by=? WHERE id=?",
                         (status, now(), reviewer.strip(), source_id))

    def videos(self):
        rows = self.db.rows("SELECT * FROM video_links ORDER BY rowid DESC")
        for row in rows:
            row["intent_tags"] = json.loads(row["intent_tags"])
        return [VideoSuggestion(**row) for row in rows]

    def save_video(self, video: VideoSuggestion):
        from app.services.video_links import valid_public_url
        if not self.product(video.product_id):
            raise ValueError("请先选择准确型号")
        if not valid_public_url(video.url, allow_demo=video.is_demo):
            raise ValueError("视频 URL 须为完整公开 HTTPS 地址；占位域名不能用于真实资料")
        if not video.title.strip() or not video.intent_tags:
            raise ValueError("视频标题和意图必填")
        if video.verified_status not in {"pending", "approved", "rejected", "deprecated"}:
            raise ValueError("无效审核状态")
        if video.verified_status == "approved":
            if video.is_demo or self.product(video.product_id)["is_demo"]:
                raise ValueError("演示链接不能批准")
            if (not video.official_source_name.strip() or not valid_public_url(video.official_source_url)
                    or not video.verified_by.strip() or video.link_status != "valid"):
                raise ValueError("批准前须核实官方出处、审核员和链接可访问性")
            video.verified_at = now()
            video.last_checked_at = now()
        values = video.model_dump()
        values["intent_tags"] = json.dumps(video.intent_tags, ensure_ascii=False)
        with self.db.connect() as conn:
            columns = list(values)
            update = ",".join(f"{key}=excluded.{key}" for key in columns if key != "video_id")
            conn.execute(f"INSERT INTO video_links ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                         f"ON CONFLICT(video_id) DO UPDATE SET {update}", tuple(values.values()))
