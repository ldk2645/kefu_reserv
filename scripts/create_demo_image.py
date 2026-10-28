"""Create a fully synthetic OCR fixture. Contains no real chat or customer data."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    fonts = [Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"),
             Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    path = next((p for p in fonts if p.exists()), None)
    if not path:
        raise SystemExit("Chinese font missing. Supply a local CJK font in this script.")
    font = ImageFont.truetype(str(path), 32)
    small = ImageFont.truetype(str(path), 24)
    image = Image.new("RGB", (1100, 480), "#edf2f6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1100, 75), fill="#1c4c62")
    draw.text((25, 20), "虚构测试会话 / 禁止用于真实客服", fill="white", font=font)
    draw.text((30, 100), "测试型号：DEMO-CAM-A", fill="#334155", font=small)
    draw.rounded_rectangle((28, 160, 920, 255), radius=16, fill="white")
    draw.text((50, 185), "这个演示摄像头怎么首次连接？", fill="#18263b", font=font)
    draw.rounded_rectangle((220, 300, 1070, 390), radius=16, fill="#c5e5df")
    draw.text((245, 325), "请人工确认买家问题和准确型号。", fill="#18263b", font=font)
    draw.text((30, 430), "纯虚构素材 · OCR 不会自动判断气泡角色", fill="#526177", font=small)
    target = ROOT / "samples/demo_chat.png"
    image.save(target)
    print("Created samples/demo_chat.png (synthetic data only).")


if __name__ == "__main__":
    main()
