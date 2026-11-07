"""Read only a freshly copied UI link; never inspect prior clipboard contents."""
import ctypes
import sys
import time

from .policy import CollectorError, safe_url


class WindowsClipboard:
    def __init__(self):
        if sys.platform != 'win32':
            raise CollectorError('WINDOWS_CLIPBOARD_REQUIRED')
        self.user = ctypes.WinDLL('user32',use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        self.user.GetClipboardSequenceNumber.restype = ctypes.c_uint32
        self.user.GetClipboardData.argtypes = [ctypes.c_uint]
        self.user.GetClipboardData.restype = ctypes.c_void_p
        self.kernel.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel.GlobalLock.restype = ctypes.c_void_p
        self.kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.kernel.GlobalSize.argtypes = [ctypes.c_void_p]
        self.kernel.GlobalSize.restype = ctypes.c_size_t

    def sequence(self):
        return self.user.GetClipboardSequenceNumber()

    def read_changed_text(self,sequence):
        if not self.user.OpenClipboard(None):
            raise CollectorError('CLIPBOARD_BUSY')
        try:
            if self.sequence() != sequence:
                raise CollectorError('CLIPBOARD_CHANGED_AGAIN')
            if not self.user.IsClipboardFormatAvailable(13):
                raise CollectorError('COPIED_LINK_NOT_TEXT')
            handle = self.user.GetClipboardData(13)
            size = self.kernel.GlobalSize(handle) if handle else 0
            if not size or size > 32768:
                raise CollectorError('COPIED_LINK_SIZE')
            pointer = self.kernel.GlobalLock(handle)
            if not pointer:
                raise CollectorError('CLIPBOARD_BUSY')
            try:
                value = ctypes.string_at(pointer,size).decode('utf-16-le').split('\0',1)[0]
            finally:
                self.kernel.GlobalUnlock(handle)
            return value
        finally:
            self.user.CloseClipboard()


def copy_visible_link(click, *, clipboard=None, timeout=2):
    """click must invoke the observed page's Copy Link button, never a player.

    The previous clipboard is not read, saved, printed or restored. Keep other
    clipboard activity paused during this short operation. Results stay pending.
    """
    clipboard = clipboard or WindowsClipboard()
    before = clipboard.sequence()
    click()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        after = clipboard.sequence()
        if after != before:
            value = clipboard.read_changed_text(after)
            if not safe_url(value):
                raise CollectorError('COPIED_LINK_UNSAFE')
            return value  # Preserve the exact link, including parameters.
        time.sleep(.1)
    raise CollectorError('COPY_LINK_NOT_CONFIRMED')
