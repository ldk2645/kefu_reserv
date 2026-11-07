from types import SimpleNamespace

import pytest

import kbs_collector.browser as browser_module
from kbs_collector.browser import Browser
from kbs_collector.policy import CollectorError


@pytest.mark.parametrize('browser',['chrome','edge'])
def test_persistent_profile_separation_and_normal_mode(tmp_path,monkeypatch,browser):
    monkeypatch.setattr(browser_module,'DATA',tmp_path)
    first=Browser(browser)
    second=Browser(browser)
    demo=Browser(browser,profile_name='demo')
    assert first.profile_path==second.profile_path
    assert first.profile_path!=demo.profile_path
    options=first.create_options()
    assert not any('headless' in a or 'incognito' in a or 'inprivate' in a for a in options.arguments)
    assert '--user-data-dir='+str(first.profile_path.resolve()) in options.arguments


@pytest.mark.parametrize('fail_start',[False,True])
def test_close_and_start_failure_preserve_profile(tmp_path,monkeypatch,fail_start):
    monkeypatch.setattr(browser_module,'DATA',tmp_path)
    browser=Browser('chrome')
    browser.profile_path.mkdir(parents=True)
    marker=browser.profile_path/'fictional-profile-marker.txt'
    marker.write_text('synthetic-data-only',encoding='utf-8')
    def create(**kwargs):
        if fail_start:
            raise RuntimeError('synthetic-start-failure')
        return SimpleNamespace(set_page_load_timeout=lambda _:None,set_script_timeout=lambda _:None,
            implicitly_wait=lambda _:None,get=lambda _:None,quit=lambda:None)
    monkeypatch.setattr(browser_module.webdriver,'Chrome',create)
    if fail_start:
        with pytest.raises(CollectorError,match='BROWSER_START_FAILED'):
            browser.start()
    else:
        browser.start()
    browser.close()
    assert marker.read_text(encoding='utf-8')=='synthetic-data-only'


def test_profile_name_cannot_escape_dedicated_directory():
    for name in ['../Default','C:/Users/account','folder/name','']:
        with pytest.raises(CollectorError,match='INVALID_PROFILE_NAME'):
            Browser(profile_name=name)
