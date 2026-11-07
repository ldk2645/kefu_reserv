"""Explicit staging -> existing product. Never approve or overwrite existing sources."""
from uuid import uuid4
from dataclasses import dataclass

from app.repositories.catalog import Catalog, now
from app.services.video_links import valid_public_url, video_intent

from .normalizer import block_text, digest, markdown
from .policy import CollectorError, exact_model_in, safe_url
from .storage import atomic_write
from .chunks import knowledge_chunks


@dataclass(frozen=True)
class BrandConfirmation:
    brand: str
    basis: str
    reviewer: str


def import_capture(storage, article_id, db, product_id, *, brand_confirmation=None):
    capture = next((c for c in storage.captures() if c.id == article_id), None)
    product = Catalog(db).product(product_id)
    if not capture or not product:
        raise CollectorError("IMPORT_SELECTION_REQUIRED")
    if capture.product.is_demo and not product["is_demo"]:
        raise CollectorError("DEMO_IMPORT_BLOCKED")
    body = "\n".join(block_text(b) for b in capture.blocks)
    brand_matches=capture.product.brand == product['brand']
    if not brand_matches and brand_confirmation:
        brand_matches=('BRAND_UNCONFIRMED' in capture.issues and
            brand_confirmation.brand.strip()==product['brand'] and
            bool(brand_confirmation.basis.strip()) and bool(brand_confirmation.reviewer.strip()))
    if ("MODEL_UNCONFIRMED" in capture.issues or capture.product.model != product["model"] or
            not brand_matches or not capture.product.model_evidence or
            capture.product.model_evidence not in body or
            not exact_model_in(capture.product.model, capture.product.model_evidence)):
        raise CollectorError("EXACT_MODEL_REQUIRED")
    if not safe_url(capture.source_url) and not capture.product.is_demo:
        raise CollectorError("UNSAFE_SOURCE_URL")
    path = storage.root/"markdown"/(capture.id+".md")
    atomic_write(path, markdown(capture))
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT source_id FROM kbs_imports WHERE article_id=? AND product_id=?", (capture.id,product_id)).fetchone()
        if existing:
            return "skipped"
        source_id = uuid4().hex
        conn.execute("""INSERT INTO knowledge_sources
            (id,product_id,kind,title,path,source_url,provenance,sha256,version,verified_status,is_demo,imported_at,local_only)
            VALUES (?,?,?,?,?,?,?,?,?,'pending',?,?,1)""", (source_id,product_id,"internal_faq",capture.title,
                str(path.resolve()),capture.source_url,"小米 KBS 人工选区采集；内部资料，官方性及适用条件待审核",
                capture.content_hash,capture.id,int(product["is_demo"] or capture.product.is_demo),now()))
        for section,text in knowledge_chunks(capture):
            conn.execute("INSERT INTO knowledge_chunks VALUES (?,?,?,?,?)", (uuid4().hex,source_id,section,None,text))
        conn.execute("INSERT INTO kbs_imports VALUES (?,?,?,?,?)", (source_id,capture.id,product_id,capture.product.model,capture.captured_at))
        if brand_confirmation:
            conn.execute('INSERT INTO kbs_product_bindings VALUES (?,?,?,?,?,?,?,?,?,?)',
                (source_id,capture.id,product_id,capture.product.brand,capture.product.model,
                 product['brand'],product['sku'],brand_confirmation.basis.strip(),brand_confirmation.reviewer.strip(),now()))
        for video in capture.videos:
            if video.get('audience') == 'internal':
                continue
            if not video["title"] or video["applicable_model"] != product["model"]:
                continue
            if not valid_public_url(video["url"], allow_demo=capture.product.is_demo):
                continue
            if conn.execute("SELECT video_id FROM video_links WHERE product_id=? AND url=?", (product_id,video["url"])).fetchone():
                continue
            video_id = "kbs-" + digest([product_id,video["url"]])
            import json
            conn.execute("""INSERT INTO video_links
                (video_id,product_id,title,url,intent_tags,verified_status,official_source_name,official_source_url,
                 customer_shareable,is_demo,link_status,local_only)
                VALUES (?,?,?,?,?,'pending',?,?,0,?,'unknown',1)""", (video_id,product_id,video["title"],video["url"],
                    json.dumps([video_intent(video["purpose"])]),"小米 KBS 页面候选；官方性待人工核实",capture.source_url,
                    int(product["is_demo"] or capture.product.is_demo)))
    return "imported_pending"
