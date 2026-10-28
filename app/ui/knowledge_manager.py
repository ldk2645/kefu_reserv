from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QPlainTextEdit, QFileDialog, QListWidget)

from app.repositories.catalog import Catalog
from app.models import VideoSuggestion
from app.services.document_import import import_document, KINDS
from app.ui.workers import Worker


class KnowledgeManager(QDialog):
    def __init__(self, db, data_dir, parent=None):
        super().__init__(parent)
        self.db, self.data_dir = db, data_dir
        self.catalog = Catalog(db)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.workers = set()
        self.setWindowTitle("知识库 · 商品 / 资料审核 / 官方教程 URL")
        self.resize(1050, 820)
        layout = QVBoxLayout(self)
        note = QLabel("资料正文不可信，须核实型号、原文和来源后批准。视频只存 URL，不下载或解析内容。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.product_tab()
        self.document_tab()
        self.video_tab()
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.refresh()

    def action(self, label, callback):
        b = QPushButton(label)
        b.clicked.connect(callback)
        return b

    def product_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.products = QListWidget()
        layout.addWidget(self.products)
        form = QFormLayout()
        self.product_fields = {}
        for key, title in [("brand", "品牌"), ("name", "商品名称"), ("model", "准确硬件型号"), ("sku", "店铺 SKU"), ("aliases", "别名（英文逗号分隔）"), ("category", "品类")]:
            field = QLineEdit()
            self.product_fields[key] = field
            form.addRow(title, field)
        layout.addLayout(form)
        layout.addWidget(self.action("新增真实商品映射", self.add_product))
        layout.addWidget(QLabel("相似标题不会自动匹配。混装套装请按部件分别建模。已有 SKU 不允许静默覆盖。"))
        self.tabs.addTab(page, "商品与型号")

    def document_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.doc_product = QComboBox()
        self.doc_kind = QComboBox()
        for key, text in KINDS.items():
            self.doc_kind.addItem(text, key)
        self.provenance = QLineEdit()
        self.provenance.setPlaceholderText("例如：厂商提供的已验证文件 / 官网说明书页面")
        self.source_url = QLineEdit()
        self.version = QLineEdit("1")
        self.effective = QLineEdit()
        self.expires = QLineEdit()
        for label, widget in [("适用型号 / SKU", self.doc_product), ("资料类别", self.doc_kind), ("来源说明（必填）", self.provenance),
            ("来源 URL（可选）", self.source_url), ("版本", self.version), ("SOP 生效日期 YYYY-MM-DD", self.effective), ("SOP 失效日期 YYYY-MM-DD", self.expires)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        self.import_button = self.action("导入 PDF / DOCX / TXT / MD（默认 pending）", self.import_file)
        layout.addWidget(self.import_button)
        self.documents = QListWidget()
        self.documents.setMaximumHeight(130)
        self.documents.currentRowChanged.connect(self.show_document)
        layout.addWidget(self.documents)
        self.doc_preview = QPlainTextEdit()
        self.doc_preview.setReadOnly(True)
        layout.addWidget(self.doc_preview)
        layout.addWidget(self.action("打开所选资料的本地原始副本", self.open_document))
        row = QHBoxLayout()
        self.source_status = QComboBox()
        self.source_status.addItems(["approved", "pending", "rejected", "deprecated"])
        self.source_reviewer = QLineEdit()
        self.source_reviewer.setPlaceholderText("审核员别名")
        self.source_checked = QCheckBox("已核实型号、原文与来源")
        row.addWidget(self.source_status)
        row.addWidget(self.source_reviewer)
        row.addWidget(self.source_checked)
        row.addWidget(self.action("保存审核", self.review_source))
        layout.addLayout(row)
        self.tabs.addTab(page, "说明书 / FAQ / SOP")

    def video_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.video_list = QListWidget()
        self.video_list.setMaximumHeight(130)
        self.video_list.currentRowChanged.connect(self.show_video)
        layout.addWidget(self.video_list)
        form = QFormLayout()
        self.video_product = QComboBox()
        self.video_title, self.video_url, self.official_name, self.official_url = [QLineEdit() for _ in range(4)]
        self.video_intent = QComboBox()
        for label, tag in [("Wi-Fi 配网", "wifi_setup"), ("蓝牙配对", "pairing"), ("安装", "installation"), ("复位", "reset"), ("清洁", "cleaning"), ("其他", "other")]:
            self.video_intent.addItem(label, tag)
        self.video_status = QComboBox()
        self.video_status.addItems(["pending", "approved", "rejected", "deprecated"])
        self.link_status = QComboBox()
        self.link_status.addItems(["unknown", "valid", "broken"])
        self.video_reviewer = QLineEdit()
        self.shareable = QCheckBox("已确认允许向客户分享")
        self.video_checked = QCheckBox("已人工打开核对官方来源、适用型号与链接内容")
        for label, widget in [("适用型号 / SKU", self.video_product), ("标题", self.video_title), ("视频 HTTPS URL", self.video_url),
            ("官方来源名称", self.official_name), ("官方来源 HTTPS 页面", self.official_url), ("咨询意图", self.video_intent),
            ("审核状态", self.video_status), ("可访问性（人工核实）", self.link_status), ("审核员别名", self.video_reviewer)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        layout.addWidget(self.shareable)
        layout.addWidget(self.video_checked)
        row = QHBoxLayout()
        row.addWidget(self.action("新建（清空编辑）", self.new_video))
        row.addWidget(self.action("保存 / 更新所选视频", self.save_video))
        layout.addLayout(row)
        layout.addWidget(QLabel("unknown / broken 都不会加入草稿。HTTP 200 不能证明内容正确；本版不主动探测链接。"))
        self.tabs.addTab(page, "官方视频 URL")
        self.edit_video_id = None

    def refresh(self):
        products = self.catalog.products()
        self.products.clear()
        self.products.addItems([f"{'[演示]' if p['is_demo'] else ''} {p['model']} / {p['sku']} / {p['name']}" for p in products])
        for combo in [self.doc_product, self.video_product]:
            old = combo.currentData()
            combo.clear()
            for p in products:
                combo.addItem(f"{'[演示]' if p['is_demo'] else ''} {p['model']} / {p['sku']}", p["id"])
            if combo.findData(old) >= 0:
                combo.setCurrentIndex(combo.findData(old))
        self.source_rows = self.catalog.sources()
        self.documents.clear()
        self.documents.addItems([f"[{s['verified_status']}] {'演示 / ' if s['is_demo'] else ''}{s['model']} / {s['title']} / v{s['version']}" for s in self.source_rows])
        self.video_rows = self.catalog.videos()
        self.video_list.clear()
        self.video_list.addItems([f"[{v.verified_status} / {v.link_status}] {v.title}" for v in self.video_rows])
        self.source_checked.setChecked(False)
        self.video_checked.setChecked(False)

    def add_product(self):
        try:
            self.catalog.add_product(**{key: field.text() for key, field in self.product_fields.items()})
            self.refresh()
            self.message.setText("商品已新增，请导入对应资料。")
        except ValueError as e:
            self.message.setText(str(e))

    def import_file(self):
        name, _ = QFileDialog.getOpenFileName(self, "导入说明书或 FAQ", "", "文档 (*.pdf *.docx *.txt *.md)")
        if not name:
            return
        args = (self.db, self.data_dir, name, self.doc_product.currentData(), self.doc_kind.currentData(),
                self.provenance.text(), self.source_url.text(), self.version.text(), self.effective.text(), self.expires.text())
        self.import_button.setEnabled(False)
        self.message.setText("正在后台解析文档…")
        worker = Worker(lambda: import_document(*args))
        self.workers.add(worker)
        worker.signals.done.connect(self.imported)
        worker.signals.failed.connect(self.message.setText)
        worker.signals.finished.connect(lambda: self.import_button.setEnabled(True))
        worker.signals.finished.connect(lambda: self.workers.discard(worker))
        self.pool.start(worker)

    def imported(self, source_id):
        self.refresh()
        for index, source in enumerate(self.source_rows):
            if source["id"] == source_id:
                self.documents.setCurrentRow(index)
        self.message.setText("导入成功，状态 pending。请审阅原文和来源后批准。")

    def selected_source(self):
        index = self.documents.currentRow()
        return self.source_rows[index] if 0 <= index < len(self.source_rows) else None

    def show_document(self, index):
        self.source_checked.setChecked(False)
        source = self.selected_source()
        if not source:
            self.doc_preview.clear()
            return
        parts = self.catalog.source_chunks(source["id"])
        self.doc_preview.setPlainText(f"型号: {source['model']}\n来源: {source['provenance']}\nURL: {source['source_url']}\n"
            f"原件: {source['path']}\nSHA256: {source['sha256']}\n审核: {source['verified_by']} {source['reviewed_at']}\n\n" +
            "\n\n".join(f"[{c['page'] or '段落'} / {c['section']}] {c['content']}" for c in parts))

    def open_document(self):
        source = self.selected_source()
        if source:
            QDesktopServices.openUrl(QUrl.fromLocalFile(source["path"]))

    def review_source(self):
        source = self.selected_source()
        if not source:
            return
        try:
            if self.source_status.currentText() == "approved" and not self.source_checked.isChecked():
                raise ValueError("批准前须勾选已核实型号、原文和来源")
            self.catalog.review_source(source["id"], self.source_status.currentText(), self.source_reviewer.text())
            self.refresh()
            self.message.setText("资料审核状态已更新。")
        except ValueError as error:
            self.message.setText(str(error))

    def new_video(self):
        self.edit_video_id = None
        for field in [self.video_title, self.video_url, self.official_name, self.official_url, self.video_reviewer]:
            field.clear()
        self.video_status.setCurrentText("pending")
        self.link_status.setCurrentText("unknown")
        self.shareable.setChecked(False)
        self.video_checked.setChecked(False)

    def show_video(self, index):
        if not 0 <= index < len(self.video_rows):
            return
        v = self.video_rows[index]
        self.edit_video_id = v.video_id
        self.video_product.setCurrentIndex(self.video_product.findData(v.product_id))
        for widget, value in [(self.video_title, v.title), (self.video_url, v.url),
            (self.official_name, v.official_source_name), (self.official_url, v.official_source_url),
            (self.video_reviewer, v.verified_by)]:
            widget.setText(value)
        self.video_intent.setCurrentIndex(self.video_intent.findData(v.intent_tags[0]))
        self.video_status.setCurrentText(v.verified_status)
        self.link_status.setCurrentText(v.link_status)
        self.shareable.setChecked(v.customer_shareable)
        self.video_checked.setChecked(False)

    def save_video(self):
        try:
            if self.video_status.currentText() == "approved" and not self.video_checked.isChecked():
                raise ValueError("批准前须人工核实并勾选确认")
            product = self.catalog.product(self.video_product.currentData())
            if not product:
                raise ValueError("请先新增商品型号")
            v = VideoSuggestion(video_id=self.edit_video_id or uuid4().hex, product_id=product["id"],
                title=self.video_title.text(), url=self.video_url.text().strip(),
                official_source_name=self.official_name.text(), official_source_url=self.official_url.text().strip(),
                intent_tags=[self.video_intent.currentData()], verified_status=self.video_status.currentText(),
                link_status=self.link_status.currentText(), verified_by=self.video_reviewer.text(),
                customer_shareable=self.shareable.isChecked(), is_demo=bool(product["is_demo"]))
            self.catalog.save_video(v)
            self.refresh()
            self.new_video()
            self.message.setText("视频已保存；仅全部门槛满足才会推荐。")
        except ValueError as error:
            self.message.setText(str(error))

    def reject(self):
        if self.pool.activeThreadCount():
            self.message.setText("文档仍在解析，请稍候关闭。")
            return
        super().reject()
