"""SRP-350III로 ESC/POS 래스터 이미지를 보내고 용지를 자른다.

Linux: CUPS 큐에 raw로 전송 (`lp -o raw`)
Windows: 설치된 프린터 드라이버에 RAW 데이터로 전송 (pywin32 필요)

환경변수
  TICKET_PRINTER   프린터(큐) 이름, 기본 SRP-350III
  TICKET_DRY_RUN=1 인쇄하지 않고 output/ 폴더에 PNG로 저장
"""
import os
import subprocess
import sys
from datetime import datetime

from PIL import Image

ESC, GS = b"\x1b", b"\x1d"
PRINTER = os.environ.get("TICKET_PRINTER", "SRP-350III")
DRY_RUN = os.environ.get("TICKET_DRY_RUN") == "1"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def raster(img: Image.Image) -> bytes:
    """GS v 0 래스터 비트 이미지 명령."""
    img = img.convert("1")
    w = (img.width + 7) // 8 * 8
    canvas = Image.new("1", (w, img.height), 1)
    canvas.paste(img, (0, 0))
    bits = bytes(b ^ 0xFF for b in canvas.tobytes())  # PIL 1=흰색, 프린터 1=검정
    return GS + b"v0\x00" + (w // 8).to_bytes(2, "little") + img.height.to_bytes(2, "little") + bits


def build_job(images: list[Image.Image]) -> bytes:
    data = ESC + b"@"
    for img in images:
        data += raster(img) + b"\n" * 4 + GS + b"V\x42\x00"  # 여백 급지 후 부분 절단
    return data


def send_raw(data: bytes) -> None:
    if sys.platform == "win32":
        import win32print  # pywin32

        h = win32print.OpenPrinter(PRINTER)
        try:
            win32print.StartDocPrinter(h, 1, ("ticket", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
    else:
        r = subprocess.run(["lp", "-d", PRINTER, "-o", "raw"], input=data, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode(errors="replace").strip() or f"lp 종료 코드 {r.returncode}")


def print_images(images: list[Image.Image], name: str = "ticket") -> None:
    if DRY_RUN:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for i, img in enumerate(images):
            img.save(os.path.join(OUTPUT_DIR, f"{datetime.now():%Y%m%d-%H%M%S}-{name}-{i}.png"))
        return
    send_raw(build_job(images))
