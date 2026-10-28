from dataclasses import asdict, dataclass
import json
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    def validate(self):
        if self.width < 8 or self.height < 8 or self.width * self.height > 20_000_000:
            raise ValueError("选区为空、太小或过大，请重新框选聊天区域")


def map_region(rect, logical_size, monitor) -> Region:
    """Map screen-local Qt logical coordinates to monitor physical pixels."""
    x, y, width, height = rect
    sx = monitor["width"] / logical_size[0]
    sy = monitor["height"] / logical_size[1]
    left, top = round(x * sx), round(y * sy)
    right, bottom = round((x + width) * sx), round((y + height) * sy)
    region = Region(monitor["left"] + left, monitor["top"] + top, right - left, bottom - top)
    region.validate()
    return region


def capture(region: Region):
    region.validate()
    import mss
    with mss.mss() as screen:
        if not any(region.left >= m["left"] and region.top >= m["top"]
                   and region.left + region.width <= m["left"] + m["width"]
                   and region.top + region.height <= m["top"] + m["height"]
                   for m in screen.monitors[1:]):
            raise ValueError("显示器布局已变化或选区跨屏，请在单块屏幕内重新框选")
        shot = screen.grab(asdict(region))
        return Image.frombytes("RGB", shot.size, shot.rgb)


def load_image(path: Path):
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("测试图片超过 25 MB")
    with Image.open(path) as image:
        if image.width * image.height > 20_000_000:
            raise ValueError("图片像素过多")
        return image.convert("RGB")


def save_region(path: Path, region: Region):
    region.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(region)), encoding="utf-8")


def load_region(path: Path):
    try:
        region = Region(**json.loads(path.read_text(encoding="utf-8")))
        region.validate()
        return region
    except (OSError, TypeError, ValueError):
        return None
