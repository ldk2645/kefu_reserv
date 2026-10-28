from pathlib import Path
from threading import Lock
import numpy as np

from app.models import OCRLine
from app.settings import ROOT


class OCRService:
    def __init__(self, engine=None):
        self.engine = engine
        self.lock = Lock()

    def _engine(self):
        if self.engine is None:
            from rapidocr import RapidOCR
            models = ROOT / "models"
            names = {"Det": "det.onnx", "Cls": "cls.onnx", "Rec": "rec.onnx"}
            if not all((models / n).is_file() for n in names.values()):
                raise ValueError("本地 OCR 模型未准备。请先运行 python scripts/prepare_ocr.py；也可手动录入问题")
            params = {f"{kind}.model_path": str(models / name) for kind, name in names.items()}
            params["Global.log_level"] = "error"
            self.engine = RapidOCR(params=params)
        return self.engine

    def recognize(self, image):
        with self.lock:
            result = self._engine()(np.array(image.convert("RGB")))
        if result is None or not getattr(result, "txts", None):
            raise ValueError("未识别到文字。请重选清晰的聊天区域，或手动录入最新买家问题")
        lines = []
        for text, box, score in zip(result.txts, result.boxes, result.scores):
            if not text.strip():
                continue
            box = np.array(box)
            lines.append(OCRLine(text=text, confidence=float(score), bbox=(
                int(box[:, 0].min()), int(box[:, 1].min()),
                int(box[:, 0].max()), int(box[:, 1].max()))))
        if not lines:
            raise ValueError("未识别到可用文字，请人工录入")
        return lines
