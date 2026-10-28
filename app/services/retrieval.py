from datetime import date
import re
from app.models import KnowledgeHit

INJECTION = re.compile(r"忽略.{0,12}(?:指令|规则|提示)|ignore.{0,30}(?:instruction|prompt)|system\s*prompt|(?:系统|开发者)指令", re.I)


def tokens(text):
    text = text.casefold()
    return set(re.findall(r"[a-z0-9_-]+", text)) | {
        run[i:i+2] for run in re.findall(r"[\u4e00-\u9fff]+", text) for i in range(len(run)-1)
    }


def retrieve(db, product_id, question, demo=False, policies=False, limit=5):
    if not product_id:
        return []
    rows = db.rows("""SELECT c.id chunk_id,s.id source_id,s.product_id,s.kind source_type,
      s.verified_status,s.title,c.section,c.page,c.content excerpt,s.path,s.source_url,s.is_demo,
      s.effective_at,s.expires_at FROM knowledge_sources s JOIN knowledge_chunks c ON c.source_id=s.id
      JOIN products p ON p.id=s.product_id WHERE s.product_id=? AND p.active=1
      AND ((s.verified_status='approved' AND s.is_demo=0 AND p.is_demo=0)
        OR (?=1 AND s.is_demo=1 AND s.verified_status='pending'))""", (product_id, int(demo)))
    query = tokens(question)
    hits = []
    for row in rows:
        if (row["source_type"] == "shop_policy") != policies:
            continue
        if policies and not (row["effective_at"] <= date.today().isoformat() <= row["expires_at"]):
            continue
        if INJECTION.search(row["excerpt"]):
            continue
        terms = tokens(row["section"] + " " + row["excerpt"])
        shared = query & terms
        if not shared:
            continue
        row["score"] = len(shared) / max(1, len(query))
        if row["is_demo"]:
            row["verified_status"] = "demo_only"
        hits.append(KnowledgeHit(**row))
    return sorted(hits, key=lambda h: (-h.score, h.source_type != "official_manual", h.chunk_id))[:min(5, limit)]
