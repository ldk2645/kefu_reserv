from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    @Slot()
    def run(self):
        try:
            self.signals.done.emit(self.function())
        except ValueError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            # Do not expose HTTP exceptions, keys, file contents, or customer text.
            self.signals.failed.emit("处理失败。请检查本地文件、OCR 模型和目录权限后重试；也可手动录入。")
        finally:
            self.signals.finished.emit()
