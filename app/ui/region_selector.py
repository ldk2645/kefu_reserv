import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.services.capture import map_region


def native_monitors():
    """Only enumerate metadata, never capture a whole monitor to select a region."""
    if sys.platform != "win32":
        raise ValueError("交互框选目前仅实现 Windows；可改用导入测试截图")
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]
    found = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32 = ctypes.windll.user32
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, callback_type, wintypes.LPARAM]
    @callback_type
    def callback(handle, dc, rect, data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcMonitor
            found[info.szDevice] = dict(left=r.left, top=r.top, width=r.right-r.left, height=r.bottom-r.top)
        return True
    user32.EnumDisplayMonitors(None, None, callback, 0)
    return found


class RegionSelector(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen, monitor):
        super().__init__()
        self.monitor = monitor
        self.start = None
        self.selection = QRect()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 25, 44, 60))
        painter.setPen(QPen(QColor("#48e2c2"), 3))
        painter.drawRect(self.selection)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(25, 40, "在本屏幕拖框选择已授权的聊天区域 · Esc 取消 · 不支持跨屏选区")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.selection = QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        self.mouseMoveEvent(event)
        r = self.selection
        try:
            region = map_region((r.x(), r.y(), r.width(), r.height()), (self.width(), self.height()), self.monitor)
        except ValueError:
            self.cancelled.emit()
        else:
            self.selected.emit(region)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
