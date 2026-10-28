from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from app.services.capture import Region, load_region, save_region, map_region
from app.services.ocr import OCRService
from app.services.conversation import Conversation


def test_empty_region_and_persistence(tmp_path):
    with pytest.raises(ValueError):
        Region(0, 0, 0, 1).validate()
    region = Region(-100, 20, 80, 90)
    save_region(tmp_path / "region.json", region)
    assert load_region(tmp_path / "region.json") == region


def test_dpi_and_negative_monitor_coordinates():
    assert map_region((10, 20, 100, 200), (1280, 720),
                      dict(left=-1920, top=0, width=1920, height=1080)) == Region(-1905, 30, 150, 300)


def test_actual_output_contract_adapter():
    result = SimpleNamespace(txts=("我的耳机连不上",), scores=(.94,),
                             boxes=np.array([[[1, 2], [101, 2], [101, 40], [1, 40]]]))
    lines = OCRService(lambda img: result).recognize(Image.new("RGB", (120, 60)))
    assert lines[0].bbox == (1, 2, 101, 40)
    assert lines[0].speaker == "unknown"


def test_empty_ocr_is_recoverable():
    with pytest.raises(ValueError, match="未识别"):
        OCRService(lambda img: None).recognize(Image.new("RGB", (120, 60)))


def test_late_response_guard():
    c = Conversation()
    ticket = c.ticket()
    assert c.accepts(ticket)
    c.changed()
    assert not c.accepts(ticket)
    ticket = c.ticket()
    c.reset()
    assert not c.accepts(ticket)
