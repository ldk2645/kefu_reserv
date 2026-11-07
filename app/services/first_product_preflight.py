"""Read-only offline preflight. Reports structure, never grants approval."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.settings import load_settings
from kbs_collector.chunks import knowledge_chunks
from kbs_collector.extractor import Capture
from kbs_collector.normalizer import block_text, now
from kbs_collector.policy import exact_model_in, safe_url
from kbs_collector.storage import atomic_write


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)


def inspect_capture(capture):
    body='\n'.join(block_text(b) for b in capture.blocks)
    chunks=knowledge_chunks(capture)
    checks={
        'real_sample':not capture.product.is_demo,
        'exact_model_evidence':bool(capture.product.model_evidence and
            'MODEL_UNCONFIRMED' not in capture.issues and
            capture.product.model_evidence in body and
            exact_model_in(capture.product.model,capture.product.model_evidence)),
        'source_url_safe':safe_url(capture.source_url),
        'frame_url_safe':safe_url(capture.frame_url),
        'has_structured_chunks':bool(chunks),
    }
    return {'article_id':capture.id,'structurally_ready':all(checks.values()),'checks':checks,
        'chunks':len(chunks),'faq':len(capture.faq),'video_candidates':len(capture.videos),
        'internal_blocks_excluded':sum(b.get('audience')=='internal' for b in capture.blocks),
        'brand_confirmation_required':'BRAND_UNCONFIRMED' in capture.issues,
        'sku_confirmation_required':True,'human_content_review_required':True,
        'status':'pending_review'}


def preflight(collection_dir,app_path):
    """Do not initialize/migrate databases or write imports, reviews or task states."""
    collection_path=Path(collection_dir)/'index.sqlite3'
    rows=[]
    if collection_path.is_file():
        with closing(readonly(collection_path)) as conn:
            rows=conn.execute('SELECT product_key,payload FROM captures ORDER BY captured_at,id').fetchall()
    latest={}
    for _,payload in rows:
        capture=Capture.model_validate_json(payload)
        key=(capture.product.name,capture.product.category,capture.frame_url,capture.root_selector)
        latest[key]=capture
    items=[inspect_capture(c) for c in latest.values()]
    application={'real_products':0,'imported_sources':0,'approved_real_sources':0}
    if Path(app_path).is_file():
        with closing(readonly(app_path)) as conn:
            application['real_products']=conn.execute('SELECT COUNT(*) FROM products WHERE is_demo=0').fetchone()[0]
            application['approved_real_sources']=conn.execute(
                'SELECT COUNT(*) FROM knowledge_sources WHERE is_demo=0 AND verified_status=?',('approved',)).fetchone()[0]
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kbs_imports'").fetchone():
                application['imported_sources']=conn.execute('SELECT COUNT(*) FROM kbs_imports').fetchone()[0]
    summary={'collection_found':collection_path.is_file(),'products':len({key for key,_ in rows}),
        'capture_versions':len(rows),'latest_pages':len(items),
        'structurally_ready_pages':sum(i['structurally_ready'] for i in items),
        'blocked_pages':sum(not i['structurally_ready'] for i in items),
        'pending_review_pages':len(items),
        'structured_chunks':sum(i['chunks'] for i in items),
        **application}
    return {'version':1,'generated_at':now(),'offline':True,'summary':summary,'items':items,
        'note':'仅检查结构及本地计数，不代表事实准确、链接有效或人工审核通过。未创建商品、导入资料或改变审核状态。'}


def main():
    settings=load_settings()
    try:
        report=preflight(settings.data_dir/'kbs_import'/'pilot_four_categories',settings.data_dir/'copilot.sqlite3')
        atomic_write(settings.data_dir/'first_product'/'preflight.json',json.dumps(report,ensure_ascii=False,indent=2))
    except Exception:
        # SQLite/pydantic exceptions can contain real paths or document bodies.
        print(json.dumps({'ok':False,'error':'LOCAL_PREFLIGHT_FAILED'}))
        return 1
    print(json.dumps({'ok':True,**report['summary']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
