from dataclasses import replace
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox,
                               QDoubleSpinBox, QLabel, QDialogButtonBox)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置 · API 默认关闭")
        self.resize(660, 420)
        layout = QVBoxLayout(self)
        self.demo = QCheckBox("使用虚构演示模式（真实客户请关闭）")
        self.demo.setChecked(settings.demo_mode)
        layout.addWidget(self.demo)
        self.enabled = QCheckBox("主动启用外部 API（每次调用均需确认脱敏预览）")
        self.enabled.setChecked(settings.ai_enabled)
        layout.addWidget(self.enabled)
        form = QFormLayout()
        self.base = QLineEdit(settings.ai_base_url)
        self.base.setPlaceholderText("https://您的服务商/v1")
        self.key = QLineEdit(settings.ai_api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.model = QLineEdit(settings.ai_model)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setValue(settings.ai_timeout_seconds)
        for label, widget in [("API 基础地址", self.base), ("API Key", self.key), ("模型名", self.model), ("超时（秒）", self.timeout)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        text = QLabel("窗口输入的密钥仅保留在本次进程内，不写盘。需要下次自动加载时，可自行在 .env 中配置。\n模型缺失、资料不足或 R2/R3 风险使用本地保守草稿。演示资料不提交 API。")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        proposed = replace(self.settings, ai_enabled=self.enabled.isChecked(), demo_mode=self.demo.isChecked(),
            ai_base_url=self.base.text().strip().rstrip("/"), ai_api_key=self.key.text().strip(),
            ai_model=self.model.text().strip(), ai_timeout_seconds=self.timeout.value())
        if proposed.ai_enabled:
            if not proposed.online_ready:
                self.error.setText("启用 API 前请完整填写地址、密钥和模型名。")
                return
            try:
                proposed.validate_endpoint()
            except ValueError as error:
                self.error.setText(str(error))
                return
        self.settings.__dict__.update(proposed.__dict__)
        self.accept()
