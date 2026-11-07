import socket
from dataclasses import asdict
import pytest

from app.models import ModelReply
from app.services.draft import prepare,generate,validate_reply
from app.settings import Settings,load_settings,ROOT


def test_legacy_online_configuration_cannot_enable_requests(catalog_fixture,tmp_path,monkeypatch):
    def deny(*args,**kwargs):
        pytest.fail('Offline application attempted a network connection')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setenv('AI_ENABLED','true')
    monkeypatch.setenv('AI_API_KEY','FICTIONAL_KEY')
    monkeypatch.setenv('AI_BASE_URL','https://fictional.test/v1')
    monkeypatch.setenv('AI_MODEL','fixture')
    monkeypatch.setenv('APP_DATA_DIR',str(tmp_path))
    env=tmp_path/'fictional.env'
    env.write_text('AI_ENABLED=true\nAI_API_KEY=OTHER_FICTIONAL_KEY\n',encoding='utf-8')
    settings=load_settings(env)
    assert not settings.online_ready and 'ai_api_key' not in asdict(settings)
    assert 'FICTIONAL_KEY' not in repr(settings)
    db,*_,ctx=catalog_fixture
    draft=generate(ctx,prepare(db,ctx),settings)
    assert draft.mode=='离线资料草稿'
    assert draft.used_knowledge_ids
    assert not (ROOT/'app/services/llm_client.py').exists()


def test_offline_mode_persists_without_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_DATA_DIR',str(tmp_path))
    Settings(data_dir=tmp_path,demo_mode=False).save_preferences()
    assert not load_settings(tmp_path/'missing.env').demo_mode
    assert 'AI_' not in (tmp_path/'preferences.json').read_text()


@pytest.mark.parametrize('changes',[
    {'used_knowledge_ids':['invented-id']},{'used_video_ids':['invented-video']},
    {'customer_reply':'去 https://unreviewed.test/video 看一下'}, {'customer_reply':'小鲸吃token了'},
    {'customer_reply':'长按复位键30秒'}, {'customer_reply':'给您赔偿500元'},
    {'customer_reply':'我已经查过您的订单'}, {'customer_reply':'视频里30秒演示了操作'},
    {'customer_reply':'这款支持无线充电和双频Wi-Fi'}, {'customer_reply':'请打开机壳拆机复位'},
    {'customer_reply':'教程地址：unreviewed.cn/video'},
])
def test_unsupported_reply_still_rejected(catalog_fixture,changes):
    db,*_,ctx=catalog_fixture
    evidence=prepare(db,ctx)
    data=dict(intent='how_to_use',risk_level='R0',missing_information=[],
        customer_reply='您好，请打开测试设置页面，然后选择测试网络。',operator_note='虚构测试',
        used_knowledge_ids=[evidence.hits[0].chunk_id],used_video_ids=[])
    data.update(changes)
    with pytest.raises(ValueError):
        validate_reply(ModelReply(**data),evidence)


def test_long_procedure_is_not_truncated_mid_step(catalog_fixture):
    db,*_,ctx=catalog_fixture
    evidence=prepare(db,ctx)
    evidence.hits[0].excerpt='虚构长步骤。'*200+'仅在满足虚构条件时操作。'
    draft=generate(ctx,evidence,Settings(demo_mode=False))
    assert '进一步核对' in draft.customer_reply
    assert '虚构长步骤' not in draft.customer_reply
    assert draft.used_knowledge_ids
