"""Only fictional products and isolated SQLite files; no real approvals."""
import json
import socket
import pytest

from test_kbs import sample_raw,sample_product
from app.repositories.db import Database
from app.repositories.catalog import Catalog
from app.services.first_product import FirstProduct
from app.services.retrieval import retrieve
from app.settings import Settings
from app.ui.first_product import FirstProductDialog
from kbs_collector.normalizer import normalize
from kbs_collector.chunks import knowledge_chunks


@pytest.fixture
def onboarding(tmp_path,sample_raw,sample_product):
    db=Database(tmp_path/'app.sqlite3')
    flow=FirstProduct(db,tmp_path)
    sample_product.brand='未明确（待审核）'
    sample_raw['blocks'].insert(3,{'kind':'field','field_name':'额定功率','value':'8 W','text':'额定功率：8 W'})
    c=normalize(sample_raw,sample_product)
    c.issues.append('BRAND_UNCONFIRMED')
    flow.store.save(c,flow.store.begin({'fictional':True}))
    return flow,c


def bind_fixture(flow,c,**kwargs):
    return flow.bind(c.id,'测试厂商','FICTIONAL-SKU-ONLY','虚构清单核对','虚构审核员',**kwargs)


def test_real_binding_requires_operator_facts_and_confirmation(onboarding):
    flow,c=onboarding
    with pytest.raises(ValueError,match='亲自核对'):
        bind_fixture(flow,c)
    with pytest.raises(ValueError,match='均必填'):
        flow.bind(c.id,'测试厂商','','虚构依据','虚构审核员',confirmed=True)
    assert not flow.catalog.products()


def test_bind_review_and_offline_reply_chain(onboarding,monkeypatch):
    flow,c=onboarding
    def deny(*args,**kwargs):
        pytest.fail('First product flow must not use the network')
    monkeypatch.setattr(socket.socket,'connect',deny)
    binding=bind_fixture(flow,c,confirmed=True)
    assert flow.catalog.sources()[0]['verified_status']=='pending'
    assert not retrieve(flow.db,binding['product_id'],'额定功率是多少')
    assert not flow.verify(binding,'额定功率是多少')['stats']['passed']
    with pytest.raises(ValueError,match='阅读原文'):
        flow.review(binding,'虚构审核员')
    flow.review(binding,'虚构审核员',confirmed=True)
    result=flow.verify(binding,'额定功率是多少')
    assert result['stats']['passed'] and '8 W' in result['draft'].customer_reply
    assert result['stats']['copy_requires_review'] and result['stats']['wrong_sku_blocked']
    assert result['draft'].requires_human_review and result['draft'].mode=='离线资料草稿'
    state=json.loads(flow.state_path.read_text(encoding='utf-8'))
    assert state['state']=='offline_verified'
    assert '额定功率是多少' not in flow.state_path.read_text(encoding='utf-8')
    assert bind_fixture(flow,c,confirmed=True)['outcome']=='skipped'
    assert len(flow.catalog.products())==1 and len(flow.catalog.sources())==1
    assert flow.catalog.sources()[0]['verified_status']=='approved'
    assert json.loads(flow.state_path.read_text(encoding='utf-8'))['state']=='approved_by_operator'


def test_binding_audit_preserves_raw_model_and_brand(onboarding):
    flow,c=onboarding
    bind_fixture(flow,c,confirmed=True)
    original=flow.store.captures()[0]
    assert original.id==c.id and original.product.brand=='未明确（待审核）'
    record=flow.db.rows('SELECT * FROM kbs_product_bindings')[0]
    assert record['original_model']==c.product.model
    assert record['original_brand']=='未明确（待审核）' and record['confirmed_brand']=='测试厂商'
    assert flow.catalog.sources()[0]['source_url']==c.source_url


def test_existing_sku_mismatch_never_overwritten(onboarding):
    flow,c=onboarding
    pid=flow.catalog.add_product('测试厂商','虚构相似商品','TEST-CAM-A2','FICTIONAL-SKU-ONLY')
    with pytest.raises(ValueError,match='不同品牌/型号'):
        bind_fixture(flow,c,confirmed=True)
    assert flow.catalog.product(pid)['model']=='TEST-CAM-A2'
    assert not flow.catalog.sources()


def test_chunks_keep_question_steps_and_conditions_together(sample_raw,sample_product):
    sample_raw['blocks']=[{'kind':'heading','level':1,'text':'虚构使用方法'},
        {'kind':'question','text':'虚构设备怎么连接？'},
        {'kind':'paragraph','text':'先满足虚构使用条件。'},
        {'kind':'step','number':1,'text':'打开虚构设置。'},
        {'kind':'note','audience':'internal','text':'FICTIONAL_OPERATOR_ONLY'},
        {'kind':'step','number':2,'text':'确认虚构连接。'},
        {'kind':'note','audience':'external','text':'仅适用虚构条件。'},
        {'kind':'question','text':'没有答案的虚构问题？'}]
    chunks=knowledge_chunks(normalize(sample_raw,sample_product))
    assert len(chunks)==1
    body=chunks[0][1]
    for value in ['怎么连接','使用条件','1. 打开','2. 确认','仅适用']:
        assert value in body
    assert 'FICTIONAL_OPERATOR_ONLY' not in body and '没有答案' not in body


def test_local_window_walks_operator_review_and_validation(onboarding,qtbot):
    flow,c=onboarding
    dialog=FirstProductDialog(flow.db,Settings(data_dir=flow.data_dir))
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert dialog.choices.count()==1
    assert not dialog.metadata_confirmed.isChecked() and not dialog.content_confirmed.isChecked()
    assert '店铺 SKU' in dialog.next_step.text()
    assert not any(button.isEnabled() for button in
        [dialog.bind_button,dialog.review_button,dialog.verify_button,dialog.use_button])
    dialog.brand.setText('测试厂商')
    dialog.sku.setText('FICTIONAL-SKU-ONLY')
    dialog.basis.setText('虚构清单')
    dialog.reviewer.setText('虚构审核员')
    assert not dialog.bind_button.isEnabled()
    dialog.metadata_confirmed.setChecked(True)
    assert dialog.bind_button.isEnabled()
    dialog.bind_button.click()
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert dialog.binding
    assert '第 2 步' in dialog.next_step.text()
    assert not dialog.review_button.isEnabled() and not dialog.verify_button.isEnabled()
    dialog.review_button.click()
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert flow.catalog.sources()[0]['verified_status']=='pending'
    dialog.content_confirmed.setChecked(True)
    dialog.review_button.click()
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert dialog.verify_button.isEnabled() and not dialog.use_button.isEnabled()
    dialog.question.setText('额定功率是多少')
    dialog.verify_button.click()
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert dialog.verification['stats']['passed'] and dialog.use_button.isEnabled()
    dialog.use_button.click()
    assert dialog.selected_product_id==dialog.binding['product_id']
    assert not dialog.settings.demo_mode


def test_reopen_uses_database_review_and_requires_fresh_verification(onboarding,qtbot):
    flow,c=onboarding
    binding=bind_fixture(flow,c,confirmed=True)
    flow.review(binding,'虚构审核员',confirmed=True)
    assert flow.verify(binding,'额定功率是多少')['stats']['passed']
    dialog=FirstProductDialog(flow.db,Settings(data_dir=flow.data_dir))
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda:not dialog.workers,timeout=5000)
    assert dialog.binding==binding and dialog.source_status=='approved'
    assert not dialog.content_confirmed.isChecked() and not dialog.metadata_confirmed.isChecked()
    assert dialog.verify_button.isEnabled() and not dialog.use_button.isEnabled()
    dialog.question.clear()
    assert not dialog.verify_button.isEnabled()
    dialog.sku.setText('FICTIONAL-CHANGED-SKU')
    assert dialog.binding is None and dialog.source_status is None
    assert not dialog.verify_button.isEnabled() and not dialog.bind_button.isEnabled()
    assert flow.catalog.sources()[0]['verified_status']=='approved'


def test_preflight_is_readonly_and_keeps_facts_out_of_report(onboarding,monkeypatch):
    from app.services.first_product_preflight import preflight
    flow,c=onboarding
    def deny(*args,**kwargs):
        pytest.fail('Preflight must remain offline')
    monkeypatch.setattr(socket.socket,'connect',deny)
    with flow.store.connect() as conn:
        before='\n'.join(conn.iterdump())
    with flow.db.connect() as conn:
        app_before='\n'.join(conn.iterdump())
    report=preflight(flow.store.root,flow.db.path)
    assert report['summary']['structurally_ready_pages']==1
    assert report['summary']['pending_review_pages']==1
    assert report['summary']['real_products']==report['summary']['imported_sources']==0
    assert report['items'][0]['brand_confirmation_required']
    for private in [c.product.name,c.product.model,c.source_url,'8 W']:
        assert private not in json.dumps(report,ensure_ascii=False)
    with flow.store.connect() as conn:
        assert before=='\n'.join(conn.iterdump())
    with flow.db.connect() as conn:
        assert app_before=='\n'.join(conn.iterdump())
    assert not flow.state_path.exists()


def test_preflight_rejects_missing_model_evidence_and_unsafe_source(onboarding):
    from app.services.first_product_preflight import inspect_capture
    _,capture=onboarding
    missing=capture.model_copy(deep=True)
    missing.product.model_evidence='虚构但不在正文中的证据'
    assert not inspect_capture(missing)['structurally_ready']
    unsafe=capture.model_copy(update={'frame_url':'https://example.invalid/?token=FICTIONAL_SECRET'})
    assert not inspect_capture(unsafe)['structurally_ready']


def test_preflight_missing_database_does_not_create_it(tmp_path):
    from app.services.first_product_preflight import preflight
    report=preflight(tmp_path/'missing_collection',tmp_path/'missing_app.sqlite3')
    assert not report['summary']['collection_found'] and not list(tmp_path.iterdir())


def test_preflight_cli_failure_does_not_print_private_validation_errors(onboarding,monkeypatch,capsys):
    import app.services.first_product_preflight as module
    flow,_=onboarding
    with flow.store.connect() as conn:
        conn.execute('UPDATE captures SET payload=?',('{"private":"FICTIONAL_PRIVATE_CANARY"}',))
    monkeypatch.setattr(module,'load_settings',lambda:Settings(data_dir=flow.data_dir))
    assert module.main()==1
    output=capsys.readouterr()
    assert 'LOCAL_PREFLIGHT_FAILED' in output.out
    assert 'FICTIONAL_PRIVATE_CANARY' not in output.out+output.err
