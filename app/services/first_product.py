"""Local operator-led first SKU import, review and offline reply verification."""
import json
from pathlib import Path
from uuid import uuid4

from app.models import ConfirmedContext
from app.repositories.catalog import Catalog
from app.services.draft import prepare,generate,review_copy
from app.settings import Settings
from kbs_collector.storage import Storage,atomic_write
from kbs_collector.importer import import_capture,BrandConfirmation
from kbs_collector.normalizer import block_text,now
from kbs_collector.policy import exact_model_in,safe_url


class FirstProduct:
    def __init__(self,db,data_dir,collection_dir=None):
        self.db=db
        self.catalog=Catalog(db)
        self.data_dir=Path(data_dir)
        self.store=Storage(collection_dir or self.data_dir/'kbs_import'/'pilot_four_categories')
        self.state_path=self.data_dir/'first_product'/'status.json'

    def candidates(self):
        latest={}
        for capture in self.store.captures():
            key=(capture.product.name,capture.product.category,capture.frame_url,capture.root_selector)
            latest[key]=capture
        return [c for c in latest.values() if not c.product.is_demo and c.product.model and
                'MODEL_UNCONFIRMED' not in c.issues and safe_url(c.source_url)]

    def selected(self,article_id):
        capture=next((c for c in self.candidates() if c.id==article_id),None)
        if not capture:
            raise ValueError('请选择最新且页面明确标注准确型号的资料。')
        return capture

    def suggested_question(self,capture):
        for block in capture.blocks:
            if (block['kind']=='field' and block.get('audience')!='internal' and
                block.get('field_name','').strip(' ：:') not in {'品牌','产品名称','名称','产品型号','型号'}):
                return '这款产品的'+block['field_name'].strip(' ：:')+'是什么？'
        return '这个产品怎么使用？'

    def bind(self,article_id,brand,sku,basis,reviewer,*,confirmed=False):
        if not confirmed:
            raise ValueError('请先亲自核对品牌、准确型号及店铺 SKU，并勾选确认。')
        capture=self.selected(article_id)
        brand,sku,basis,reviewer=(v.strip() for v in (brand,sku,basis,reviewer))
        if not all((brand,sku,basis,reviewer)) or brand=='未明确（待审核）':
            raise ValueError('真实品牌、店铺 SKU、核对依据和审核员别名均必填。')
        if any(len(v)>500 for v in (brand,sku,basis,reviewer)):
            raise ValueError('核对信息过长，请填写简短说明，不填客户或订单信息。')
        if 'BRAND_UNCONFIRMED' not in capture.issues and brand!=capture.product.brand:
            raise ValueError('填写的品牌与页面明确品牌不同，不能直接覆盖。')
        body='\n'.join(block_text(b) for b in capture.blocks)
        if capture.product.model_evidence not in body or not exact_model_in(capture.product.model,capture.product.model_evidence):
            raise ValueError('型号证据未通过核对，请重新检查原文。')
        existing=next((p for p in self.catalog.products() if p['sku']==sku),None)
        if existing and (existing['is_demo'] or existing['model']!=capture.product.model or existing['brand']!=brand):
            raise ValueError('该 SKU 已绑定不同品牌/型号或演示商品，未作修改。')
        product_id=existing['id'] if existing else self.catalog.add_product(
            brand,capture.product.name,capture.product.model,sku,category=capture.product.category)
        try:
            outcome=import_capture(self.store,article_id,self.db,product_id,
                brand_confirmation=BrandConfirmation(brand,basis,reviewer))
        except Exception:
            if not existing:
                with self.db.connect() as conn:
                    conn.execute('DELETE FROM products WHERE id=? AND NOT EXISTS (SELECT 1 FROM knowledge_sources WHERE product_id=?)',
                                 (product_id,product_id))
            raise
        source_id=self.db.rows('SELECT source_id FROM kbs_imports WHERE article_id=? AND product_id=?',(article_id,product_id))[0]['source_id']
        binding={'article_id':article_id,'product_id':product_id,'source_id':source_id,'outcome':outcome}
        self.record(binding,'approved_by_operator' if self.binding_status(binding)=='approved' else 'imported_pending')
        return binding

    def binding_status(self,binding):
        rows=self.db.rows('''SELECT s.verified_status FROM knowledge_sources s
            JOIN kbs_imports i ON i.source_id=s.id JOIN products p ON p.id=s.product_id
            WHERE s.id=? AND i.article_id=? AND i.product_id=? AND p.active=1''',
            (binding['source_id'],binding['article_id'],binding['product_id']))
        return rows[0]['verified_status'] if rows else None

    def review(self,binding,reviewer,*,confirmed=False):
        if not confirmed:
            raise ValueError('请阅读原文及知识片段，亲自确认适用范围后再批准。')
        self.catalog.review_source(binding['source_id'],'approved',reviewer)
        self.record(binding,'approved_by_operator')
        return self.binding_status(binding)

    def verify(self,binding,question):
        if not question.strip():
            raise ValueError('请填写一个需要验证的典型问题。')
        product=self.catalog.product(binding['product_id'])
        if not product:
            raise ValueError('商品不存在或已停用。')
        context=ConfirmedContext(session_local_id=uuid4().hex,confirmed_by_user=True,
            latest_customer_message=question,product_id=product['id'],sku=product['sku'])
        evidence=prepare(self.db,context)
        draft=generate(context,evidence,Settings(data_dir=self.data_dir,demo_mode=False))
        matching=[h for h in evidence.hits if h.source_id==binding['source_id']]
        used=any(h.chunk_id in draft.used_knowledge_ids for h in matching)
        copy_blocked=False
        try:
            review_copy(self.db,draft,context,draft.customer_reply,False,False)
        except ValueError:
            copy_blocked=True
        wrong_sku_blocked=False
        try:
            prepare(self.db,context.model_copy(update={'sku':product['sku']+'__wrong__'}))
        except ValueError:
            wrong_sku_blocked=True
        passed=bool(used and copy_blocked and wrong_sku_blocked)
        stats={'passed':passed,'matching_source_hits':len(matching),'draft_uses_selected_source':used,
               'copy_requires_review':copy_blocked,'wrong_sku_blocked':wrong_sku_blocked,'offline':True}
        self.record(binding,'offline_verified' if passed else 'verification_pending',verification=stats)
        return {'stats':stats,'evidence':evidence,'draft':draft,'context':context}

    def record(self,binding,state,**extra):
        # IDs and aggregate checks only; never persist customer questions or drafts.
        atomic_write(self.state_path,json.dumps({'version':1,'state':state,'updated_at':now(),
            'binding':binding,**extra},ensure_ascii=False,indent=2))
