"""Separate local control window. All Selenium and disk work runs off the GUI thread."""
import json

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QCheckBox, QPlainTextEdit, QSplitter, QScrollArea, QSizePolicy)

from app.ui.workers import Worker
from app.repositories.db import Database
from app.repositories.catalog import Catalog
from app.settings import load_settings

from .browser import Browser
from .extractor import Product
from .importer import import_capture
from .navigator import Navigator
from .normalizer import normalize
from .policy import CollectorError, source_allowed
from .storage import atomic_write

MESSAGES = {
    "BROWSER_START_FAILED":"浏览器启动失败。请检查浏览器/驱动版本；若同一配置已占用，请使用已有采集窗口或正常关闭后重试，不要删除登录目录。可用 --driver 指定官方驱动。",
    "MANUAL_LOGIN_REQUIRED":"请在浏览器手动登录，并勾选登录确认。",
    "LOGIN_OR_SCOPE_REQUIRED":"当前不在允许的知识库页面，或地址含认证参数。请人工进入产品页面。",
    "ACCESS_RESTRICTED":"检测到验证、权限限制或禁止采集提示，已暂停。请人工检查；若规则禁止采集，请退出并使用获准的人工导出。",
    "LOAD_TIMEOUT":"选区未出现或仍在变化。请检查 iframe/选区、等待加载，再手动重试；未刷新页面。",
    "INSPECT_FIRST":"请先检查当前页面结构，再选择实际正文区域。",
    "PAGE_CHANGED":"读取过程中页面变化，请重新检查结构。",
    "FRAME_CHANGED":"iframe 已变化，请重新检查结构。",
    "PILOT_PRODUCT_LIMIT":"本轮最多 5 个不同产品；批量采集尚未开放。",
    "PILOT_PAGE_LIMIT":"本轮最多 100 个资料版本，请先完成人工验收。",
    "EXACT_MODEL_REQUIRED":"品牌或准确型号不一致，或缺少页面内型号证据；禁止套用相似型号。",
    "DEMO_IMPORT_BLOCKED":"虚构演示采集资料不能导入真实商品。",
    "EMPTY_CONTENT":"没有可用正文，请重选正文区域。",
}


class CollectorWindow(QWidget):
    def __init__(self, storage, browser="chrome", driver_path=None, start_url=None, fixture=False):
        super().__init__()
        self.storage, self.fixture, self.start_url = storage, fixture, start_url
        self.browser = Browser(browser, driver_path, headless=False,profile_name="demo" if fixture else "kbs")
        self.navigator = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.workers = set()
        self.raw = self.task_id = None
        self.frames_data = []
        self.shutdown = False
        self.setWindowTitle("小鲸 · 小米 KBS 本地采集 V0.1" + ("【虚构演示】" if fixture else ""))
        self.resize(1100, 860)
        layout = QVBoxLayout(self)
        self.status = QLabel("先打开有头浏览器并手动登录。本轮最多 5 个产品；正文和链接始终待人工审核。")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        layout.addWidget(self.status)
        self.controls = QWidget()
        form_layout = QVBoxLayout(self.controls)
        self.authorization = QCheckBox("已获公司授权，站点规则允许；当前仅为产品资料，无个人或经营数据")
        self.login = QCheckBox("已手动登录（或正在使用虚构演示页）")
        form_layout.addWidget(self.authorization)
        form_layout.addWidget(self.login)
        bar = QHBoxLayout()
        self.add_button(bar,"1 打开浏览器",self.open_browser)
        self.add_button(bar,"2 检查当前结构",self.inspect)
        self.add_button(bar,"检查指定正文结构",self.inspect_region)
        self.add_button(bar,"重新生成本地报告",self.report)
        form_layout.addLayout(bar)
        form = QFormLayout()
        self.tab = QComboBox()
        self.tab.addItem("浏览器标签页 1",0)
        tab_row = QHBoxLayout()
        tab_row.addWidget(self.tab)
        self.add_button(tab_row,"刷新标签页数量",self.refresh_tabs)
        self.add_button(tab_row,"切换选中标签页",self.select_tab)
        form.addRow("浏览器标签页",tab_row)
        self.frames = QComboBox()
        self.frames.currentIndexChanged.connect(self.frame_selected)
        form.addRow("实际 iframe 路径",self.frames)
        self.roots = QComboBox()
        self.roots.setEditable(True)
        form.addRow("实际正文 CSS 选择器",self.roots)
        form_layout.addLayout(form)
        split = QSplitter()
        product_widget = QWidget()
        product_form = QFormLayout(product_widget)
        self.product_fields = {}
        for key,label in [("brand","品牌（按页面原文）"),("name","产品名称（按页面原文）"),
                          ("model","准确型号；不明确时留空"),("category","品类"),("model_evidence","页面中含准确型号的原文短句")]:
            field = QLineEdit()
            self.product_fields[key] = field
            product_form.addRow(label,field)
        if fixture:
            for key,value in dict(brand="演示品牌",name="虚构摄像头",model="DEMO-CAM-A",category="虚构摄像头",model_evidence="型号： DEMO-CAM-A").items():
                self.product_fields[key].setText(value)
        self.capture_checked = QCheckBox("已核对选区、准确型号、完整性和链接；保存为待审核")
        product_form.addRow(self.capture_checked)
        capture_bar = QHBoxLayout()
        self.add_button(capture_bar,"3 读取选区并预览",self.preview_capture)
        self.add_button(capture_bar,"4 保存待审核",self.save_capture)
        product_form.addRow(capture_bar)
        self.scroll_selector = QLineEdit()
        self.scroll_selector.setPlaceholderText("实际可滚动容器的 CSS 选择器；网页分页/展开/标签可手动操作")
        product_form.addRow("局部滚动容器",self.scroll_selector)
        self.add_button(product_form,"向下滚动一次",self.scroll)
        self.resume_list = QComboBox()
        product_form.addRow("失败 / 中断任务",self.resume_list)
        self.add_button(product_form,"载入恢复信息",self.resume)
        self.resume_url = QLineEdit()
        self.resume_url.setReadOnly(True)
        product_form.addRow("恢复地址（复制后手动打开）",self.resume_url)
        self.article_list = QComboBox()
        self.product_list = QComboBox()
        product_form.addRow("已采集文章",self.article_list)
        self.add_button(product_form,"预览已采集文章",self.preview_saved)
        product_form.addRow("小鲸现有商品 / SKU",self.product_list)
        self.add_button(product_form,"刷新本地待导入列表",self.refresh_imports)
        self.import_checked = QCheckBox("已核对原始型号与 SKU，追加导入为 pending 待审核")
        product_form.addRow(self.import_checked)
        self.add_button(product_form,"追加导入所选文章",self.import_selected)
        product_scroll = QScrollArea()
        product_scroll.setWidgetResizable(True)
        product_scroll.setWidget(product_widget)
        split.addWidget(product_scroll)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("本地结构和正文预览，不发送任何模型。\n先检查结构，再选择 iframe 与正文根节点。")
        split.addWidget(self.preview)
        form_layout.addWidget(split,1)
        layout.addWidget(self.controls,1)
        for field in self.product_fields.values():
            field.textChanged.connect(lambda _:self.capture_checked.setChecked(False))
        self.frames.currentIndexChanged.connect(lambda _:self.abandon_preview())
        self.roots.currentTextChanged.connect(lambda _:self.abandon_preview())
        self.article_list.currentIndexChanged.connect(lambda _:self.import_checked.setChecked(False))
        self.product_list.currentIndexChanged.connect(lambda _:self.import_checked.setChecked(False))
        self.refresh_local_lists()

    @staticmethod
    def add_button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        if isinstance(layout,QFormLayout):
            layout.addRow(button)
        else:
            layout.addWidget(button)
        return button

    def run(self, function, done):
        if self.workers:
            return
        self.controls.setEnabled(False)
        def safe_call():
            try:
                return {"value":function()}
            except CollectorError as exc:
                return {"error":exc.code}
            except Exception:
                return {"error":"DRIVER_OR_DATA_ERROR"}
        worker = Worker(safe_call)
        self.workers.add(worker)
        def completed(result):
            if "error" in result:
                code = result["error"]
                self.status.setText(MESSAGES.get(code,"操作失败（"+code+"）。请检查选区、驱动或本地文件后手动重试。未输出原始错误。"))
                if code in {"ACCESS_RESTRICTED","LOGIN_OR_SCOPE_REQUIRED"}:
                    self.login.setChecked(False)
                    self.authorization.setChecked(False)
            else:
                done(result["value"])
        worker.signals.done.connect(completed)
        def finished():
            self.workers.discard(worker)
            self.controls.setEnabled(True)
            if self.shutdown:
                self.close()
        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    def permitted(self):
        if not self.navigator or not self.authorization.isChecked() or not self.login.isChecked():
            self.status.setText("请先打开浏览器、手动登录，并确认公司授权及站点规则允许。")
            return False
        return True

    def open_browser(self):
        if self.navigator:
            self.status.setText("浏览器已打开。请在可见窗口中操作；登录信息仅由你输入。")
            return
        def open_it():
            driver = self.browser.start(self.start_url) if self.start_url else self.browser.start()
            return Navigator(driver,fixture=self.fixture)
        def opened(navigator):
            self.navigator = navigator
            self.status.setText("普通浏览器已打开，将复用独立的本地登录数据。若网站要求登录，请手动完成；程序不填写或读取认证字段。")
        self.run(open_it,opened)

    def abandon_preview(self):
        # New inspection makes a previous unsaved selection ineligible for saving.
        self.raw = None
        self.capture_checked.setChecked(False)

    def inspect(self):
        if not self.permitted():
            return
        self.abandon_preview()
        def inspect_it():
            self.browser.wait_for_manual_login(confirmed=True)
            report = self.navigator.inspect()
            atomic_write(self.storage.root/"structure.json",json.dumps(report,ensure_ascii=False,indent=2))
            return report
        def inspected(report):
            self.frames_data = report["frames"]
            self.frames.clear()
            for item in self.frames_data:
                self.frames.addItem("主文档" if not item["path"] else "iframe " + "/".join(map(str,item["path"])),item["path"])
            self.preview.setPlainText(json.dumps(report,ensure_ascii=False,indent=2))
            self.status.setText("只读检查完成。请按实际栏目进入产品页；页面变化后重新检查，选择正文根节点。结构报告仅保存在本地。")
        self.run(inspect_it,inspected)

    def frame_selected(self,index):
        self.roots.clear()
        if 0 <= index < len(self.frames_data):
            for root in self.frames_data[index]["roots"]:
                self.roots.addItem(root["selector"])

    def inspect_region(self):
        if not self.permitted():
            return
        frame = self.frames.currentData() or []
        selector = self.roots.currentText().strip()
        if not selector:
            self.status.setText('请先填写实际观察到的正文 CSS 选择器，再检查指定区域。')
            return
        self.abandon_preview()
        def inspect_it():
            self.browser.wait_for_manual_login(confirmed=True)
            root = self.navigator.inspect_region(frame,selector)
            report = {'source_url':self.browser.driver.current_url,'frames':[{'path':frame,'roots':[root]}]}
            atomic_write(self.storage.root/'structure.json',json.dumps(report,ensure_ascii=False,indent=2))
            return report
        def inspected(report):
            self.frames_data=report['frames']
            self.frames.clear()
            self.frames.addItem('主文档' if not frame else 'iframe '+ '/'.join(map(str,frame)),frame)
            self.preview.setPlainText(json.dumps(report,ensure_ascii=False,indent=2))
            self.status.setText('指定正文结构检查完成，可以读取选区；未读取其他区域。')
        self.run(inspect_it,inspected)

    def preview_saved(self):
        article_id=self.article_list.currentData()
        if not article_id:
            return
        self.abandon_preview()
        def read():
            return next(c for c in self.storage.captures() if c.id==article_id).model_dump_json(indent=2)
        self.run(read,lambda value:self.preview.setPlainText(value))

    def preview_capture(self):
        if not self.permitted():
            return
        frame, selector = self.frames.currentData(), self.roots.currentText().strip()
        if frame is None or not selector:
            self.status.setText("请先检查结构并选定 iframe 和正文根节点。")
            return
        fields = {k:v.text().strip() for k,v in self.product_fields.items()}
        self.abandon_preview()
        def capture_it():
            url = self.browser.driver.current_url
            if not source_allowed(url,fixture=self.fixture):
                raise CollectorError("LOGIN_OR_SCOPE_REQUIRED")
            spec = {"source_url":url,"frame":frame,"selector":selector,"product":fields,"is_demo":self.fixture}
            task_id = self.storage.begin(spec)
            try:
                raw = self.navigator.extract(frame,selector)
                return task_id,raw
            except Exception as exc:
                self.storage.fail(task_id,exc.code if isinstance(exc,CollectorError) else "DRIVER_OR_DATA_ERROR")
                raise
        def captured(result):
            self.task_id,self.raw = result
            self.preview.setPlainText(json.dumps(self.raw,ensure_ascii=False,indent=2))
            self.status.setText("已读取所选可见 DOM。请核对正文，按原文填写品牌、名称、型号及型号证据，再勾选保存。隐藏/未加载标签请逐一打开采集。")
        self.run(capture_it,captured)

    def save_capture(self):
        if not self.raw or not self.capture_checked.isChecked() or not self.permitted():
            self.status.setText("请读取选区、核对预览并勾选确认。")
            return
        raw,task_id = self.raw,self.task_id
        fields = {k:v.text().strip() for k,v in self.product_fields.items()}
        def save_it():
            try:
                capture = normalize(raw,Product(**fields,is_demo=self.fixture),fixture=self.fixture)
                outcome = self.storage.save(capture,task_id)
                return outcome, json.loads((self.storage.root/"crawl_manifest.json").read_text(encoding="utf-8"))
            except Exception as exc:
                self.storage.fail(task_id,exc.code if isinstance(exc,CollectorError) else "SAVE_FAILED")
                raise
        def saved(result):
            self.abandon_preview()
            self.show_report(result[1])
            self.refresh_local_lists()
        self.run(save_it,saved)

    def refresh_local_lists(self):
        self.resume_list.clear()
        for task in self.storage.pending_tasks():
            self.resume_list.addItem(task["id"][:10]+" · "+task["state"]+" · "+task["error_code"],task)
        self.article_list.clear()
        for c in self.storage.summaries():
            self.article_list.addItem(c["model"]+" · "+c["title"],c["id"])

    def refresh_imports(self):
        def read():
            settings = load_settings()
            return Catalog(Database(settings.data_dir/"copilot.sqlite3")).products()
        def loaded(products):
            self.refresh_local_lists()
            self.product_list.clear()
            for p in products:
                self.product_list.addItem(p["brand"]+" / "+p["model"]+" / "+p["sku"],p["id"])
            self.import_checked.setChecked(False)
        self.run(read,loaded)

    def import_selected(self):
        article,product = self.article_list.currentData(),self.product_list.currentData()
        if not article or not product or not self.import_checked.isChecked():
            self.status.setText("请先在小鲸知识库中建立准确商品，刷新列表，核对并勾选追加导入。")
            return
        def perform():
            settings = load_settings()
            return import_capture(self.storage,article,Database(settings.data_dir/"copilot.sqlite3"),product)
        self.run(perform,lambda result:self.status.setText("导入结果："+result+"。请在小鲸知识库界面审核；这些资料始终禁止进入外部模型。"))

    def resume(self):
        task = self.resume_list.currentData()
        if not task:
            return
        spec = json.loads(task["spec"])
        self.resume_url.setText(spec["source_url"])
        for k,v in spec["product"].items():
            self.product_fields[k].setText(v)
        self.preview.setPlainText(json.dumps(spec,ensure_ascii=False,indent=2))
        self.status.setText("请复制恢复地址，在已登录浏览器中手动打开。重新检查结构，选回 iframe " + str(spec["frame"]) + " 和选区，再读取保存。已保存内容会去重。")

    def report(self):
        self.run(self.storage.export,self.show_report)

    def show_report(self,report):
        self.status.setText("本地累计：成功 {}，失败尝试 {}，跳过重复 {}，待审核 {}，产品 {}/5。报告：{}".format(
            report["success"],report["failed"],report["skipped"],report["pending_review"],report["products"],self.storage.root/"crawl_manifest.json"))

    def refresh_tabs(self):
        if not self.navigator:
            return
        def loaded(count):
            self.tab.clear()
            for i in range(count):
                self.tab.addItem("浏览器标签页 "+str(i+1),i)
        self.run(lambda:len(self.browser.driver.window_handles),loaded)

    def select_tab(self):
        if not self.navigator:
            return
        index = self.tab.currentData()
        self.abandon_preview()
        self.run(lambda:self.navigator.select_tab(index),lambda _:self.status.setText("已切换浏览器标签页；请重新检查结构。"))

    def scroll(self):
        if not self.permitted() or not self.scroll_selector.text().strip():
            return
        frame,selector = self.frames.currentData(),self.scroll_selector.text().strip()
        if frame is None:
            return
        self.abandon_preview()
        self.run(lambda:self.navigator.scroll(frame,selector),lambda _:self.status.setText("已局部滚动一次；请等内容加载完成后重新检查/读取。虚拟列表请逐段保存，不能保证未显示内容完整。"))

    def closeEvent(self,event):
        if self.workers:
            self.status.setText("后台操作正在完成，请稍候关闭；不会在任务中途销毁浏览器。")
            event.ignore()
        elif self.browser.driver and not self.shutdown:
            event.ignore()
            self.shutdown = True
            self.run(self.browser.close,lambda _:None)
        else:
            event.accept()
