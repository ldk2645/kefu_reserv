"""Visible offline rehearsal with fictional data, real OCR and an in-memory copy sink.

Never opens the real collection, captures the desktop, or touches the system clipboard.
"""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.pop('QT_QPA_PLATFORM',None)

from PIL import Image,ImageDraw,ImageFont
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.repositories.db import Database
from app.services.first_product import FirstProduct
from app.settings import Settings
from app.ui.main_window import MainWindow
from kbs_collector.extractor import Product
from kbs_collector.normalizer import normalize


def fixture(data_dir):
    """Production flags exercise real-mode gates only in a new fictional database."""
    db=Database(data_dir/'copilot.sqlite3')
    flow=FirstProduct(db,data_dir)
    raw={'source_url':'https://kbs.be.xiaomi.com/fictional/acceptance',
        'frame_url':'https://kbs.be.xiaomi.com/fictional/acceptance',
        'page_title':'纯虚构验收资料','title':'虚构参数','frame_path':[],
        'root_selector':'#fictional','characters':100,'displayed_times':[],'links':[],
        'blocks':[{'kind':'heading','level':1,'text':'虚构参数'},
            {'kind':'field','field_name':'产品型号','value':'FICTIONAL-OFFLINE-A',
                'text':'产品型号：FICTIONAL-OFFLINE-A'},
            {'kind':'field','field_name':'额定功率','value':'8 W','text':'额定功率：8 W'}]}
    capture=normalize(raw,Product(brand='虚构品牌',name='虚构验收设备',model='FICTIONAL-OFFLINE-A',
        model_evidence='产品型号：FICTIONAL-OFFLINE-A',category='虚构验收'))
    flow.store.save(capture,flow.store.begin({'fictional_acceptance':True}))
    binding=flow.bind(capture.id,'虚构品牌','FICTIONAL-ACCEPTANCE-SKU',
        '纯虚构验收夹具','虚构审核员',confirmed=True)
    pending_excluded=not flow.verify(binding,'额定功率是多少')['stats']['passed']
    flow.review(binding,'虚构审核员',confirmed=True)
    return db,flow,binding,pending_excluded


def synthetic_question():
    paths=[Path('C:/Windows/Fonts/msyh.ttc'),Path('C:/Windows/Fonts/simhei.ttf'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    font_path=next((p for p in paths if p.is_file()),None)
    if font_path is None:
        raise RuntimeError('CJK_FONT_MISSING')
    font=ImageFont.truetype(str(font_path),32)
    image=Image.new('RGB',(1000,220),'white')
    draw=ImageDraw.Draw(image)
    draw.text((24,25),'纯虚构测试，请勿发送真实客户',font=font,fill='black')
    draw.text((24,110),'额定功率是多少？',font=font,fill='black')
    return image


def main():
    report_dir=ROOT/'test-results'
    data_dir=report_dir/('offline-acceptance-'+uuid4().hex)
    state={'ok':False,'stage':'setup','fictional_only':True,'system_clipboard_used':False,
        'network_attempts':0,'checks':{}}
    start=time.monotonic()
    application=QApplication([])
    state['platform']=application.platformName()
    copies=[]
    window=None

    def deny(*args,**kwargs):
        state['network_attempts']+=1
        raise RuntimeError('OFFLINE_NETWORK_ATTEMPT')

    with ExitStack() as stack:
        for owner,name in [(socket.socket,'connect'),(socket.socket,'connect_ex'),
                           (socket.socket,'sendto'),(socket,'create_connection')]:
            stack.enter_context(patch.object(owner,name,deny))
        try:
            db,flow,binding,pending_excluded=fixture(data_dir)
            state['checks']['pending_source_excluded']=pending_excluded
            window=MainWindow(Settings(data_dir=data_dir,demo_mode=False),db,clipboard_writer=copies.append)
            window.setWindowTitle('【纯虚构演练】小鲸离线全流程')
            window.banner.setText('纯虚构自动演练 · 不用于真实客户 · 复制只进入测试内存')
            window.product.setCurrentIndex(window.product.findData(binding['product_id']))
            window.show()
            window.recognize_image(synthetic_question())
            state['stage']='ocr'
            timer=QTimer()

            def finish(error=None):
                if error:
                    state['error']=error
                state['ok']=not error and all(state['checks'].values()) and state['network_attempts']==0
                timer.stop()
                application.quit()

            def require(value,code):
                if not value:
                    raise RuntimeError(code)
                state['checks'][code]=True

            def poll():
                try:
                    if time.monotonic()-start>45:
                        finish('TIMEOUT')
                        return
                    if window.workers:
                        return
                    if state['stage']=='ocr':
                        rows=[r for r in range(window.ocr_table.rowCount())
                            if '额定功率' in window.ocr_table.item(r,0).text()]
                        require(bool(rows),'real_ocr_recognized_question')
                        window.use_ocr_line(rows[0])
                        require(not window.generate_button.isEnabled(),'question_confirmation_required')
                        window.confirmed.setChecked(True)
                        window.generate_button.click()
                        state['stage']='draft'
                    elif state['stage']=='draft':
                        draft=window.conversation.draft
                        require(bool(draft and draft.used_knowledge_ids and '8 W' in window.reply.toPlainText()),
                            'approved_source_used')
                        require(draft.mode=='离线资料草稿' and not draft.is_demo,'offline_real_mode')
                        require(any(h.source_id==binding['source_id'] for h in window.evidence.hits),
                            'exact_source_visible')
                        window.copy_reply()
                        require(not copies and not window.copy_button.isEnabled(),'copy_requires_review')
                        window.reviewed.setChecked(True)
                        window.copy_button.click()
                        require(len(copies)==1 and copies[-1]==window.reply.toPlainText(),'reviewed_copy_to_memory')
                        window.reply.setPlainText(window.reply.toPlainText()+'\n谢谢。')
                        require(not window.reviewed.isChecked() and not window.copy_button.isEnabled(),
                            'editing_revokes_reply_review')
                        window.copy_reply()
                        require(len(copies)==1,'edited_reply_not_copied')
                        # Render only our fictional QWidget; never capture a desktop region.
                        window.centralWidget().widget().grab().save(str(report_dir/'offline-acceptance-window.png'))
                        flow.catalog.review_source(binding['source_id'],'deprecated','虚构审核员')
                        window.reviewed.setChecked(True)
                        window.copy_reply()
                        require(len(copies)==1,'withdrawn_source_blocks_copy')
                        window.question.setPlainText('虚构的另一位客户问题')
                        require(draft.stale and not window.copy_button.isEnabled(),'changed_question_invalidates_draft')
                        previous_session=window.conversation.session_id
                        window.new_session()
                        require(window.conversation.session_id!=previous_session and
                            window.conversation.draft is None and window.image is None and
                            not window.question.toPlainText() and not window.context_edit.toPlainText() and
                            not window.reply.toPlainText() and not window.sources.toPlainText() and
                            window.ocr_table.rowCount()==0,'new_session_clears_previous_customer')
                        state['stage']='complete'
                        finish()
                except Exception as error:
                    # Fixture-only codes; never print an exception traceback or document content.
                    code=str(error)
                    finish(code if code.isascii() and code.replace('_','').isalnum() else 'ACCEPTANCE_FAILED')

            timer.timeout.connect(poll)
            timer.start(100)
            application.exec()
        except Exception:
            state['error']='SETUP_FAILED_CHECK_LOCAL_DEPENDENCIES_MODELS_AND_FONTS'
        finally:
            if window:
                window.pool.waitForDone()
                window.close()
            copies.clear()
    state['elapsed_seconds']=round(time.monotonic()-start,2)
    report_dir.mkdir(exist_ok=True)
    (report_dir/'offline-acceptance.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(state,ensure_ascii=False))
    return 0 if state['ok'] else 1


def run_bounded():
    # A stuck native OCR thread cannot be cancelled safely inside Qt. Limit only
    # this isolated rehearsal process; no running customer application is touched.
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],
            timeout=60,check=False,capture_output=True,text=True,encoding='utf-8')
        if result.returncode in (0,1) and result.stdout.strip():
            print(result.stdout.strip())
            return result.returncode
        error='ACCEPTANCE_PROCESS_FAILED'
    except subprocess.TimeoutExpired:
        error='ACCEPTANCE_PROCESS_TIMEOUT'
    report={'ok':False,'error':error,'fictional_only':True,'system_clipboard_used':False}
    target=ROOT/'test-results'/'offline-acceptance.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 1


if __name__=='__main__':
    raise SystemExit(main() if sys.argv[1:]==['--worker'] else run_bounded())
