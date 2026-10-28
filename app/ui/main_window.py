from pathlib import Path
from uuid import uuid4
from dataclasses import replace
import json

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QSplitter, QPlainTextEdit, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QDialog, QDialogButtonBox, QGroupBox, QScrollArea)

from app.models import ConfirmedContext
from app.repositories.catalog import Catalog
from app.services.capture import capture, load_image, load_region, save_region
from app.services.conversation import Conversation
from app.services.demo import seed_demo
from app.services.ocr import OCRService
from app.services.draft import prepare, generate, build_payload, review_copy
from app.settings import ROOT, load_yaml
from app.ui.workers import Worker

STYLE = """
QMainWindow, QDialog { background: #f2f5f8; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #203047; }
QGroupBox { border: 1px solid #d9e1ea; border-radius: 8px; margin-top: 10px; padding: 12px; font-weight: 600; background: white; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; }
QPushButton { background: #e8eef5; border: 1px solid #cbd7e4; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #d9e9f4; }
QPushButton:disabled { color: #8a97a5; background: #eef1f5; }
QPushButton#primary { color: white; background: #176f85; border: 0; font-weight: 600; }
QPlainTextEdit, QComboBox, QTableWidget, QLineEdit { background: white; border: 1px solid #ccd7e2; border-radius: 4px; padding: 5px; }
QLabel#title { font-size: 23px; font-weight: 700; color: #16566c; }
QLabel#banner { background: #fff0cf; padding: 9px; border-radius: 5px; color: #7c5309; }
"""


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    item.clicked.connect(callback)
    return item


class MainWindow(QMainWindow):
    def __init__(self, settings, db):
        super().__init__()
        self.settings, self.db = settings, db
        seed_demo(db, settings.data_dir)
        self.catalog = Catalog(db)
        self.conversation = Conversation()
        self.ocr_service = OCRService()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.workers = set()
        self.selectors = []
        self.image = self.evidence = None
        self.capture_id = ""
        self.region_path = settings.data_dir / "region.json"
        self.region = load_region(self.region_path)
        self.setWindowTitle("小鲸 · PDD 视觉 AI 客服副驾驶")
        self.resize(1240, 920)
        self.setMinimumSize(980, 740)
        self.setStyleSheet(STYLE)
        self._build()
        self.refresh_products()
        self._mode_banner()
        self._state("idle")

    def _build(self):
        central = QWidget()
        central.setMinimumHeight(850)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 15, 20, 15)
        header = QHBoxLayout()
        title = QLabel("小鲸  /  视觉客服副驾驶")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        top = QCheckBox("窗口置顶")
        top.toggled.connect(self._topmost)
        header.addWidget(top)
        header.addWidget(button("设置", self.open_settings))
        header.addWidget(button("知识库与视频", self.open_knowledge))
        root.addLayout(header)
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        root.addWidget(self.banner)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        actions = QHBoxLayout()
        for label, callback in [("选择 / 重选聊天区域", self.select_region), ("识别当前选区", self.capture_current),
            ("导入测试截图", self.import_image), ("载入虚构演示截图", self.load_demo), ("新会话", self.new_session)]:
            actions.addWidget(button(label, callback))
        root.addLayout(actions)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QGroupBox("1  屏幕 / 本地 OCR")
        left_layout = QVBoxLayout(left)
        self.preview = QLabel("截图仅保存在内存\n选择区域或导入测试图片")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(155)
        left_layout.addWidget(self.preview)
        self.ocr_table = QTableWidget(0, 3)
        self.ocr_table.setHorizontalHeaderLabels(["原文（角色未知，双击选择）", "置信度", "坐标"])
        self.ocr_table.horizontalHeader().setStretchLastSection(True)
        self.ocr_table.setColumnWidth(0, 260)
        self.ocr_table.setMinimumHeight(130)
        self.ocr_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ocr_table.cellDoubleClicked.connect(self.use_ocr_line)
        left_layout.addWidget(self.ocr_table)
        left_layout.addWidget(QLabel("OCR 不判断左右气泡角色；请人工选择、纠错。"))
        right = QGroupBox("2  人工确认问题与型号")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("最新买家问题（可编辑）"))
        self.question = QPlainTextEdit()
        self.question.setPlaceholderText("双击左侧 OCR 行，或直接录入最新买家问题")
        self.question.setMaximumHeight(100)
        right_layout.addWidget(self.question)
        right_layout.addWidget(QLabel("必要上下文 / 已尝试步骤（可选，不自动填入全部 OCR）"))
        self.context_edit = QPlainTextEdit()
        self.context_edit.setMaximumHeight(75)
        right_layout.addWidget(self.context_edit)
        self.product = QComboBox()
        right_layout.addWidget(self.product)
        self.confirmed = QCheckBox("已确认最新买家问题、必要上下文和当前型号")
        right_layout.addWidget(self.confirmed)
        generation = QHBoxLayout()
        self.search_button = button("检索知识", self.search)
        self.generate_button = button("生成 / 重新生成回复", self.generate_reply, True)
        generation.addWidget(self.search_button)
        generation.addWidget(self.generate_button)
        right_layout.addLayout(generation)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([540, 620])
        root.addWidget(splitter, 3)
        results = QGroupBox("3  来源、风险与待审核回复")
        results_layout = QVBoxLayout(results)
        self.sources = QPlainTextEdit()
        self.sources.setReadOnly(True)
        self.sources.setMaximumHeight(135)
        self.sources.setPlaceholderText("引用原文、来源文件、页码、风险与视频审核状态将在这里显示")
        results_layout.addWidget(self.sources)
        video_row = QHBoxLayout()
        self.include_video = QCheckBox("生成时附上合格的官方教程（最多一条）")
        self.include_video.setChecked(True)
        video_row.addWidget(self.include_video)
        video_row.addStretch()
        video_row.addWidget(button("从草稿移除教程 URL", self.remove_video))
        results_layout.addLayout(video_row)
        self.reply = QPlainTextEdit()
        self.reply.setPlaceholderText("所有回复都需要人工复核；可直接编辑")
        self.reply.setMinimumHeight(115)
        results_layout.addWidget(self.reply, 1)
        self.operator_note = QLabel("操作员备注只显示在这里，不会复制给客户。")
        self.operator_note.setTextFormat(Qt.TextFormat.PlainText)
        self.operator_note.setWordWrap(True)
        results_layout.addWidget(self.operator_note)
        review_row = QHBoxLayout()
        self.reviewed = QCheckBox("我已审核当前回复、资料和链接")
        review_row.addWidget(self.reviewed)
        review_row.addStretch()
        self.copy_button = button("审核并复制", self.copy_reply, True)
        review_row.addWidget(self.copy_button)
        results_layout.addLayout(review_row)
        root.addWidget(results, 3)
        root.addWidget(QLabel("复制 ≠ 发送。请到 PDD 粘贴并由本人发送。新客户进入时点击“新会话”。"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self.question.textChanged.connect(self.context_changed)
        self.context_edit.textChanged.connect(self.context_changed)
        self.product.currentIndexChanged.connect(self.context_changed)
        self.confirmed.toggled.connect(self.update_buttons)
        self.reviewed.toggled.connect(self.update_buttons)
        self.reply.textChanged.connect(self.reply_changed)
        self.update_buttons()

    def _topmost(self, enabled):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def _mode_banner(self):
        mode = "虚构演示模式：演示资料禁止用于真实客户" if self.settings.demo_mode else "真实资料模式：仅使用经人工批准的资料"
        backend = "在线 API 已配置（每次发送先预览）" if self.settings.online_ready else "本地 Mock · 无远端模型调用"
        self.banner.setText(mode + "  |  " + backend)

    def _state(self, state, detail=""):
        phrase = load_yaml("persona.yaml")["operator_persona"]["states"].get(state, "")
        self.status.setText("小鲸 · " + phrase + ("  " + detail if detail else ""))

    def show_error(self, text):
        self._state("error", text)

    def refresh_products(self):
        old = self.product.currentData()
        self.product.blockSignals(True)
        self.product.clear()
        self.product.addItem("型号不确定（只追问，不套用相似型号）", None)
        for item in self.catalog.products():
            if not self.settings.demo_mode and item["is_demo"]:
                continue
            label = ("【虚构演示】" if item["is_demo"] else "") + item["model"] + " / " + item["sku"] + " / " + item["name"]
            self.product.addItem(label, item["id"])
        self.product.setCurrentIndex(max(0, self.product.findData(old)))
        self.product.blockSignals(False)

    def current_context(self):
        product = self.catalog.product(self.product.currentData())
        return ConfirmedContext(session_local_id=self.conversation.session_id, capture_id=self.capture_id,
            confirmed_by_user=self.confirmed.isChecked(), latest_customer_message=self.question.toPlainText().strip(),
            conversation_context=self.context_edit.toPlainText().strip(), product_id=product["id"] if product else None,
            sku=product["sku"] if product else None)

    def context_changed(self, *args):
        self.conversation.changed()
        self.confirmed.setChecked(False)
        self.reviewed.setChecked(False)
        self.evidence = None
        self.sources.clear()
        if self.conversation.draft:
            self.operator_note.setText("当前问题 / 型号 / 上下文已改变，旧草稿失效，请重新生成。")
        self.update_buttons()

    def reply_changed(self):
        self.reviewed.setChecked(False)
        self.update_buttons()

    def update_buttons(self, *args):
        valid = self.confirmed.isChecked() and bool(self.question.toPlainText().strip())
        self.generate_button.setEnabled(valid)
        self.search_button.setEnabled(valid)
        self.copy_button.setEnabled(bool(self.reviewed.isChecked() and self.conversation.can_copy(self.current_context())))

    def run_task(self, function, callback):
        ticket = self.conversation.ticket()
        worker = Worker(function)
        self.workers.add(worker)
        worker.signals.done.connect(lambda result: callback(result) if self.conversation.accepts(ticket) else None)
        worker.signals.failed.connect(lambda error: self.show_error(error) if self.conversation.accepts(ticket) else None)
        worker.signals.finished.connect(lambda: self.workers.discard(worker))
        self.pool.start(worker)
        return worker

    def new_session(self):
        self.conversation.reset()
        self.image = self.evidence = None
        self.capture_id = ""
        self.question.clear()
        self.context_edit.clear()
        self.product.setCurrentIndex(0)
        self.reply.clear()
        self.sources.clear()
        self.ocr_table.setRowCount(0)
        self.preview.clear()
        self.preview.setText("新会话 · 请重新识别或录入")
        self.confirmed.setChecked(False)
        self.reviewed.setChecked(False)
        self.operator_note.setText("上一会话的上下文和草稿已清空。")
        self._state("idle")
        self.update_buttons()

    def select_region(self):
        from app.ui.region_selector import RegionSelector, native_monitors
        try:
            monitors = native_monitors()
            for screen in QApplication.screens():
                if screen.name() in monitors:
                    overlay = RegionSelector(screen, monitors[screen.name()])
                    overlay.selected.connect(self.region_selected)
                    overlay.cancelled.connect(self.cancel_selection)
                    self.selectors.append(overlay)
            if not self.selectors:
                raise ValueError("无法匹配显示器")
            self.hide()
            for selector in self.selectors:
                selector.show()
                selector.activateWindow()
        except Exception:
            self.cancel_selection()
            self.show_error("无法打开选区。可导入测试图；请检查显示器配置或系统权限。")

    def cancel_selection(self):
        for selector in self.selectors:
            selector.close()
            selector.deleteLater()
        self.selectors = []
        self.show()

    def region_selected(self, region):
        self.region = region
        save_region(self.region_path, region)
        self.cancel_selection()
        self._state("idle", "选区已保存。点击“识别当前选区”时才截图。")

    def capture_current(self):
        if self.region is None:
            self.show_error("请先选择聊天区域")
            return
        self.confirmed.setChecked(False)
        self.reviewed.setChecked(False)
        self.hide()
        QTimer.singleShot(180, self._capture_after_hide)

    def _capture_after_hide(self):
        region = self.region
        worker = self.run_task(lambda: capture(region), self._captured)
        worker.signals.finished.connect(self.show)

    def _captured(self, image):
        self.show()
        self.recognize_image(image)

    def import_image(self):
        name, _ = QFileDialog.getOpenFileName(self, "导入本地测试截图", str(ROOT / "samples"), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if name:
            self.run_task(lambda: load_image(Path(name)), self.recognize_image)

    def load_demo(self):
        if not self.settings.demo_mode:
            self.show_error("请在设置中启用虚构演示模式")
            return
        self.new_session()
        self.product.setCurrentIndex(self.product.findData("DEMO-001"))
        path = ROOT / "samples/demo_chat.png"
        if path.exists():
            self.recognize_image(load_image(path))
        else:
            self.show_error("演示截图缺失，请运行 python scripts/create_demo_image.py")

    def recognize_image(self, image):
        self.image = image
        self.capture_id = uuid4().hex
        self.confirmed.setChecked(False)
        self.reviewed.setChecked(False)
        self.ocr_table.setRowCount(0)
        pixmap = QPixmap.fromImage(ImageQt(image))
        self.preview.setPixmap(pixmap.scaled(500, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self._state("scanning")
        self.run_task(lambda: self.ocr_service.recognize(image), self.ocr_finished)

    def ocr_finished(self, lines):
        self.ocr_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            for col, text in enumerate([line.text, f"{line.confidence:.1%}", str(line.bbox)]):
                self.ocr_table.setItem(row, col, QTableWidgetItem(text))
        self._state("idle", "识别完成。请双击买家问题对应行，纠错后勾选确认。")

    def use_ocr_line(self, row, column=0):
        item = self.ocr_table.item(row, 0)
        if item:
            self.question.setPlainText(item.text())

    def search(self):
        ctx, demo = self.current_context(), self.settings.demo_mode
        self.run_task(lambda: prepare(self.db, ctx, demo), self.display_evidence)

    def display_evidence(self, evidence):
        self.evidence = evidence
        entries = [evidence.risk.risk_level + " · " + "；".join(evidence.risk.reasons)]
        for hit in evidence.hits + evidence.policies:
            entries.append(f"[{hit.verified_status}] {hit.title} / {hit.section} / 页码 {hit.page or '无（段落）'}\n"
                f"ID: {hit.chunk_id}\n原文: {hit.excerpt}\n本地副本: {hit.path}\n来源: {hit.source_url or '人工导入文件'}")
        for v in evidence.videos:
            entries.append(f"[approved · 人工核实可访问] {v.title}\n{v.url}")
        if not evidence.videos:
            entries.append("无满足型号、意图、审核与可访问性门槛的官方视频。候选请在知识库中人工核对。")
        self.sources.setPlainText("\n\n".join(entries))
        self._state("high_risk" if evidence.risk.risk_level >= "R2" else "knowledge_hit" if evidence.hits else "model_unknown")

    def generate_reply(self):
        ctx, demo = self.current_context(), self.settings.demo_mode
        self.run_task(lambda: prepare(self.db, ctx, demo), lambda evidence: self._generate_prepared(ctx, evidence))

    def _generate_prepared(self, context, evidence):
        self.display_evidence(evidence)
        payload = None
        if self.settings.online_ready and not evidence.is_demo and evidence.risk.risk_level == "R0":
            payload = build_payload(context, evidence)
            if not self.preview_payload(payload):
                self._state("idle", "已取消在线调用，没有发送数据。")
                return
        settings, video = replace(self.settings), self.include_video.isChecked()
        self._state("idle", "正在生成草稿…")
        self.run_task(lambda: generate(context, evidence, settings, payload, include_video=video), self.draft_finished)

    def preview_payload(self, payload):
        dialog = QDialog(self)
        dialog.setWindowTitle("发送前预览 · 人工确认脱敏数据")
        dialog.resize(760, 650)
        layout = QVBoxLayout(dialog)
        note = QLabel("仅下方数据将提交给您配置的模型服务。脱敏可能遗漏姓名/地址，请检查；取消后可修改输入重试。\n目标：" + self.settings.ai_base_url)
        note.setWordWrap(True)
        layout.addWidget(note)
        editor = QPlainTextEdit(json.dumps(payload, ensure_ascii=False, indent=2))
        editor.setReadOnly(True)
        layout.addWidget(editor)
        reviewed = QCheckBox("我已检查隐私，并授权本次发送")
        layout.addWidget(reviewed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认发送")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        reviewed.toggled.connect(buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def draft_finished(self, draft):
        if draft.context_fingerprint != self.current_context().fingerprint:
            return
        self.conversation.draft = draft
        self.reply.setPlainText(draft.customer_reply)
        self.operator_note.setText(draft.mode + " | " + draft.risk_level + " | " + draft.operator_note)
        self.update_buttons()
        self._state("idle", "草稿已生成，请复核后勾选审核并复制。")

    def remove_video(self):
        text = self.reply.toPlainText()
        for video in self.evidence.videos if self.evidence else []:
            text = text.replace("\n官方教程：" + video.url, "").replace(video.url, "")
        self.reply.setPlainText(text)

    def copy_reply(self):
        try:
            text = review_copy(self.db, self.conversation.draft, self.current_context(), self.reply.toPlainText(),
                               self.reviewed.isChecked(), self.settings.demo_mode)
            QApplication.clipboard().setText(text)
            self._state("copied", "请到 PDD 粘贴发送。")
        except ValueError as error:
            self.show_error(str(error))

    def open_settings(self):
        from app.ui.settings_dialog import SettingsDialog
        if SettingsDialog(self.settings, self).exec() == QDialog.DialogCode.Accepted:
            self.new_session()
            self.refresh_products()
            self._mode_banner()

    def open_knowledge(self):
        from app.ui.knowledge_manager import KnowledgeManager
        KnowledgeManager(self.db, self.settings.data_dir, self).exec()
        self.refresh_products()
        self.context_changed()

    def closeEvent(self, event):
        self.conversation.reset()
        self.pool.clear()
        if self.pool.activeThreadCount():
            self.show_error("后台任务尚在结束，请稍候再关闭（API 有超时限制）。")
            event.ignore()
            return
        self.image = None
        event.accept()
