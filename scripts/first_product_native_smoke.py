"""Visible Windows test, fictional data only; never reads the real collection."""
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.pop('QT_QPA_PLATFORM',None)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.repositories.db import Database
from app.settings import Settings
from app.ui.first_product import FirstProductDialog
from app.ui.main_window import STYLE
from kbs_collector.extractor import Product
from kbs_collector.normalizer import normalize
from kbs_collector.storage import Storage


def main():
    report_dir=ROOT/'test-results'
    data_dir=report_dir/('first-product-native-'+uuid4().hex)
    store=Storage(data_dir/'kbs_import/pilot_four_categories')
    raw={'source_url':'https://kbs.be.xiaomi.com/fictional/native',
         'frame_url':'https://kbs.be.xiaomi.com/fictional/native','page_title':'虚构接入测试',
         'title':'虚构参数资料','frame_path':[],'root_selector':'#fictional','characters':100,
         'displayed_times':[],'links':[],
         'blocks':[{'kind':'heading','level':1,'text':'虚构参数'},
             {'kind':'field','field_name':'产品型号','value':'FICTIONAL-PWR-A','text':'产品型号：FICTIONAL-PWR-A'},
             {'kind':'field','field_name':'额定功率','value':'8 W','text':'额定功率：8 W'}]}
    product=Product(brand='虚构品牌',name='虚构流程设备',model='FICTIONAL-PWR-A',
                    model_evidence='产品型号：FICTIONAL-PWR-A',category='虚构流程测试')
    c=normalize(raw,product)
    store.save(c,store.begin({'fictional':True}))
    app=QApplication([])
    dialog=FirstProductDialog(Database(data_dir/'copilot.sqlite3'),Settings(data_dir=data_dir))
    dialog.setWindowTitle('【纯虚构测试】首个商品接入')
    dialog.setStyleSheet(STYLE)
    dialog.show()
    start=time.monotonic()
    state={'stage':'load','ok':False,'platform':app.platformName()}
    def poll():
        if time.monotonic()-start>30:
            state['error']='TIMEOUT'
            timer.stop()
            app.quit()
            return
        if dialog.workers:
            return
        if state['stage']=='load':
            dialog.sku.setText('FICTIONAL-NATIVE-SKU')
            dialog.basis.setText('纯虚构测试清单')
            dialog.reviewer.setText('虚构审核员')
            dialog.metadata_confirmed.setChecked(True)
            dialog.bind_button.click()
            state['stage']='bind'
        elif state['stage']=='bind' and dialog.binding:
            state['pending_before_review']=dialog.service.catalog.sources()[0]['verified_status']=='pending'
            dialog.content_confirmed.setChecked(True)
            dialog.review_button.click()
            state['stage']='review'
        elif state['stage']=='review':
            dialog.question.setText('额定功率是多少')
            dialog.verify_button.click()
            state['stage']='verify'
        elif state['stage']=='verify' and dialog.verification:
            state.update(dialog.verification['stats'])
            state['ok']=state['pending_before_review'] and state['passed']
            state['stage']='render'
            timer.stop()
            QTimer.singleShot(250,render)
    def render():
        dialog.grab().save(str(report_dir/'first-product-native.png'))
        dialog.use_button.click()
        app.quit()
    timer=QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    app.exec()
    dialog.pool.waitForDone(5000)
    state['elapsed_seconds']=round(time.monotonic()-start,2)
    (report_dir/'first-product-native.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps(state))
    return 0 if state['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
