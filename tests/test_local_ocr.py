from pathlib import Path
import socket
import pytest
from PIL import Image
from app.services.ocr import OCRService
from app.settings import ROOT


@pytest.fixture(scope="session")
def local_ocr():
    if not all((ROOT / "models" / name).exists() for name in ["det.onnx", "cls.onnx", "rec.onnx"]):
        pytest.skip("Run scripts/prepare_ocr.py to enable real OCR tests")
    return OCRService()


@pytest.mark.ocr
def test_real_chinese_image_with_network_denied(local_ocr, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("OCR must not access network")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    with Image.open(ROOT / "samples/demo_chat.png") as image:
        lines = local_ocr.recognize(image)
    text = "\n".join(line.text for line in lines)
    assert "首次连接" in text
    assert "DEMO-CAM-A" in text
    assert all(line.speaker == "unknown" for line in lines)
    assert all(0 <= line.confidence <= 1 for line in lines)


@pytest.mark.ocr
def test_real_blank_image(local_ocr):
    with pytest.raises(ValueError, match="未识别"):
        local_ocr.recognize(Image.new("RGB", (640, 300), "white"))
