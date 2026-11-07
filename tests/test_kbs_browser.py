"""Opt-in REAL headed Windows browser tests against fictional loopback HTML only."""
import os
from uuid import uuid4

import pytest
from selenium.webdriver.common.by import By

from kbs_collector.browser import Browser
from kbs_collector.demo import start_demo
from kbs_collector.extractor import Product
from kbs_collector.navigator import Navigator
from kbs_collector.normalizer import normalize
from kbs_collector.policy import CollectorError
from kbs_collector.storage import Storage

pytestmark = [pytest.mark.browser,pytest.mark.skipif(os.environ.get("KBS_HEADED_TEST") != "1",reason="Set KBS_HEADED_TEST=1 for visible browser fixture tests")]


@pytest.fixture(scope="module")
def live_browser():
    server,url = start_demo()
    browser = Browser(os.environ.get("KBS_TEST_BROWSER","chrome"),os.environ.get("KBS_TEST_DRIVER"),headless=False,
                      profile_name="test-"+uuid4().hex)
    try:
        driver = browser.start(url)
        yield driver,url
    finally:
        browser.close()
        server.shutdown()
        server.server_close()


def test_headed_nested_iframe_three_products_and_storage(live_browser,tmp_path):
    driver,url = live_browser
    assert "HeadlessChrome" not in driver.execute_script("return navigator.userAgent")
    nav = Navigator(driver,fixture=True)
    structure = nav.inspect()
    assert [f["path"] for f in structure["frames"]] == [[],[0],[0,0]]
    assert any(r["selector"] == "#demo-article" for r in structure["frames"][2]["roots"])
    raw = nav.extract([0,0],"#demo-article")
    assert "HIDDEN_PRIVATE_TEXT" not in str(raw) and "FORM_PRIVATE_VALUE" not in str(raw)
    assert any(b.get("text") == "异步加载章节" for b in raw["blocks"])
    assert any(b["kind"] == "step" and b["number"] == 2 for b in raw["blocks"])
    store = Storage(tmp_path)
    for index,(file,selector,name,model) in enumerate([
        (None,"#demo-article","虚构摄像头","DEMO-CAM-A"),
        ("cleaner.html","#demo-cleaner","虚构清洁设备","DEMO-CLEAN-B"),
        ("earbuds.html","#demo-earbuds","虚构耳机","DEMO-EAR-C")]):
        if file:
            driver.get(url.rsplit("/",1)[0]+"/"+file)
            nav.inspect()
            raw = nav.extract([],selector)
        product = Product(brand="演示品牌",name=name,model=model,category=name,model_evidence="型号： "+model,is_demo=True)
        c = normalize(raw,product,fixture=True)
        assert "MODEL_UNCONFIRMED" not in c.issues
        assert c.faq and c.videos and c.videos[0]["applicable_model"] == model
        assert store.save(c,store.begin({"fixture":index})) == "success"
        assert store.save(c,store.begin({"fixture":index})) == "skipped"
    report = store.export()
    assert (report["success"],report["skipped"],report["pending_review"]) == (3,3,3)


def test_spa_tab_scroll_guard_and_missing_root(live_browser):
    driver,url = live_browser
    driver.get(url.rsplit("/",1)[0]+"/article.html")
    nav = Navigator(driver,fixture=True,timeout=3)
    with pytest.raises(CollectorError,match="INSPECT_FIRST"):
        nav.extract([],"#demo-article")
    nav.inspect()
    with pytest.raises(CollectorError,match="LOAD_TIMEOUT"):
        nav.extract([],"#missing")
    driver.execute_script("location.hash = '/fictional-spa-page'")
    with pytest.raises(CollectorError,match="INSPECT_FIRST"):
        nav.extract([],"#demo-article")
    nav.inspect()
    nav.scroll([],"#demo-article")
    driver.switch_to.new_window("tab")
    driver.get(url.rsplit("/",1)[0]+"/restricted.html")
    with pytest.raises(CollectorError,match="ACCESS_RESTRICTED"):
        nav.inspect()
    nav.select_tab(0)
    assert "restricted" not in driver.current_url


def test_observed_layout_keeps_fields_sections_and_faq(live_browser):
    driver,url = live_browser
    driver.get(url.rsplit('/',1)[0]+'/structured_product.html')
    nav=Navigator(driver,fixture=True)
    nav.inspect()
    raw=nav.extract([],'.right-panel')
    product=Product(brand='虚构测试品牌',name='虚构结构设备',model='DEMO-LAYOUT-01',
                    model_evidence='产品型号：DEMO-LAYOUT-01',is_demo=True)
    captured=normalize(raw,product,fixture=True)
    assert 'MODEL_UNCONFIRMED' not in captured.issues
    assert any(b.get('field_name')=='产品型号' and b['value']=='DEMO-LAYOUT-01' for b in captured.blocks)
    assert any(b['kind']=='note' and b['audience']=='internal' for b in captured.blocks)
    assert '虚构复制按钮' not in str(captured.blocks)
    assert '虚构复制控件' not in str(captured.blocks)
    assert len(captured.faq)==2
    assert captured.faq[0]['section']==['常见问题']
    assert '1. 打开虚构设置。' in captured.faq[0]['answer']
    assert captured.faq[1]['answer']==['仅用于测试的回答二。']


def test_detail_editor_scope_and_internal_notes(live_browser):
    driver,url=live_browser
    driver.get(url.rsplit('/',1)[0]+'/detail_editor.html')
    nav=Navigator(driver,fixture=True)
    # Hidden SPA history must not trip the visible-DOM limit.
    nav.inspect()
    with pytest.raises(CollectorError,match='ROOT_TOO_BROAD'):
        nav.inspect_region([],'body')
    structure=nav.inspect_region([],'.tree-editor-container')
    assert structure['paragraphs']==4
    raw=nav.extract([],'.tree-editor-container')
    c=normalize(raw,Product(brand='虚构品牌',name='虚构设备',model='DEMO-DETAIL-01',
        model_evidence='型号： DEMO-DETAIL-01',is_demo=True),fixture=True)
    for marker in ['FICTIONAL_STAFF_INFO','FICTIONAL_OPERATOR_CONTROL','FICTIONAL_PRIVATE_TAG',
                   'FICTIONAL_FLOATING_CONTROLS','FICTIONAL_COMMENT_PERSON','FICTIONAL_HIDDEN_PAGE']:
        assert marker not in str(c.blocks)
    assert len(c.faq)==1 and '2. 打开虚构设置。' in c.faq[0]['answer']
    assert 'FICTIONAL_INTERNAL_NOTE' not in str(c.faq)
    assert any(b.get('audience')=='internal' and b.get('text')=='FICTIONAL_INTERNAL_NOTE' for b in c.blocks)
    assert len(c.videos)==2 and c.videos[1]['audience']=='internal'
    assert c.videos[0]['url'].endswith('?part=2#demo')


def test_normal_browser_retains_synthetic_cookie_after_restart():
    # Only a fictional loopback cookie. No actual website authentication is read.
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    class FixtureHandler(BaseHTTPRequestHandler):
        issued=False
        def log_message(self,*args):
            pass
        def do_GET(self):
            self.send_response(200)
            if self.path=='/set' and not FixtureHandler.issued:
                self.send_header('Set-Cookie','kbs_synthetic_fixture=fictional; Max-Age=3600; Path=/; SameSite=Lax')
                FixtureHandler.issued=True
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.end_headers()
            present='kbs_synthetic_fixture=fictional' in self.headers.get('Cookie','')
            self.wfile.write(b'fixture-cookie-present' if present else b'fixture-cookie-absent')
    server=ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler)
    Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    profile_name='restart-test-'+uuid4().hex
    kwargs=dict(browser=os.getenv('KBS_TEST_BROWSER','chrome'),driver_path=os.getenv('KBS_TEST_DRIVER'),profile_name=profile_name)
    first,second=Browser(**kwargs),Browser(**kwargs)
    try:
        driver=first.start(base+'/set')
        driver.get(base+'/check')
        assert driver.find_element(By.TAG_NAME,'body').text=='fixture-cookie-present'
        first.close()
        assert first.profile_path.is_dir()
        driver=second.start(base+'/check')
        assert second.profile_path==first.profile_path
        assert driver.find_element(By.TAG_NAME,'body').text=='fixture-cookie-present'
    finally:
        first.close()
        second.close()
        server.shutdown()
        server.server_close()
