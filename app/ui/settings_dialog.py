from PySide6.QtWidgets import QDialog,QVBoxLayout,QCheckBox,QLabel,QDialogButtonBox


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置 · 离线客服助手")
        self.resize(540, 220)
        layout = QVBoxLayout(self)
        self.demo = QCheckBox("使用虚构演示模式（真实客户请关闭）")
        self.demo.setChecked(settings.demo_mode)
        layout.addWidget(self.demo)
        text = QLabel("小鲸在本机识别文字、检索已审核资料并生成待审核草稿。\n无需模型账号或密钥。真实商品资料须先核对型号并审核。")
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
        previous=self.settings.demo_mode
        self.settings.demo_mode=self.demo.isChecked()
        try:
            self.settings.save_preferences()
        except OSError:
            self.settings.demo_mode=previous
            self.error.setText('无法保存本地设置，请检查数据目录权限。')
            return
        self.accept()
