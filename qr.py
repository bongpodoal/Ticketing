"""QR 코드 생성."""
import qrcode
from PIL import Image


def make_qr(payload: str, size: int = 150) -> Image.Image:
    """payload를 담은 흑백 QR 이미지를 약 size 픽셀 크기로 만든다 (도트가 뭉개지지 않게 정수배 확대)."""
    q = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(payload)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("L")
    scale = max(1, size // img.width)
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)
