"""입력 데이터를 영수증 양식(docs/영수증 출력 양식.pdf) 이미지로 만든다.

한글이 프린터 내장 폰트에 의존하지 않도록 PC 폰트로 그린 흑백 이미지를 출력한다.
"""
import os
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from qr import make_qr

WIDTH = 512  # SRP-350III: 80mm 용지, 인쇄폭 72mm @ 180dpi
PAD = 16
BORDER = 3

CENTER_NAME = "원주국민체육센터"
NOTICE = "이용시간은 1일 1회, 최대 2시간입니다."

# 시설명 -> 영수증에 QR을 넣을지 (양식상 수영 입장권에는 QR이 없음)
FACILITIES = {"헬스1": True, "헬스2": True, "수영": False}
GENDERS = ("남자", "여자")
ENTRY_TYPES = {"member": "회원입장", "daily": "일일입장"}
ISSUE_TYPES = {"normal": "락카번호", "waiting": "대기번호"}

_FONT_CANDIDATES = {
    "regular": [
        os.environ.get("TICKET_FONT_REGULAR", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/malgun.ttf",
    ],
    "bold": [
        os.environ.get("TICKET_FONT_BOLD", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "C:/Windows/Fonts/malgunbd.ttf",
    ],
}


def _font(weight, size):
    for path in _FONT_CANDIDATES[weight]:
        if path and os.path.exists(path):
            # Noto CJK .ttc의 1번 폰트가 KR
            return ImageFont.truetype(path, size, index=1 if path.endswith(".ttc") else 0)
    raise FileNotFoundError(f"한글 {weight} 폰트를 찾을 수 없습니다. TICKET_FONT_{weight.upper()} 환경변수를 지정하세요.")


F_HEAD = _font("bold", 26)
F_TITLE = _font("bold", 52)
F_LABEL = _font("bold", 36)
F_NUM = _font("bold", 110)
F_INFO = _font("regular", 24)
F_NOTE = _font("regular", 22)
F_ORG = _font("bold", 34)


@dataclass
class Ticket:
    entry_type: str  # "member" | "daily"
    facility: str  # FACILITIES 키
    gender: str  # "남자" | "여자"
    issue_type: str  # "normal" | "waiting"
    number: int  # 락카번호 또는 대기번호
    ticket_id: str = ""
    member_id: str = ""
    member_name: str = ""
    start_date: str = ""
    end_date: str = ""
    fee: int = 0
    printed_at: datetime = field(default_factory=datetime.now)


def mask_name(name: str) -> str:
    """이상재 -> 이*재, 김철 -> 김*"""
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def info_lines(t: Ticket) -> list[str]:
    printed = f"출력일시: {t.printed_at:%Y-%m-%d %H:%M}"
    if t.entry_type == "member":
        return [
            f"회원번호: {t.member_id}",
            f"회원명: {mask_name(t.member_name)}",
            f"유효기간: {t.start_date} ~ {t.end_date}",
            printed,
        ]
    return [f"이용료: {t.fee:,}원", printed]


def render(t: Ticket) -> Image.Image:
    """영수증 한 장을 1비트 이미지로 그린다."""
    img = Image.new("L", (WIDTH, 1200), 255)
    d = ImageDraw.Draw(img)
    left, right = PAD, WIDTH - PAD
    cx = WIDTH // 2
    y = PAD + 14

    def center(text, f, gap):
        nonlocal y
        box = d.textbbox((0, 0), text, font=f)
        d.text((cx - (box[2] - box[0]) // 2 - box[0], y - box[1]), text, font=f, fill=0)
        y += (box[3] - box[1]) + gap

    center(ENTRY_TYPES[t.entry_type], F_HEAD, 22)
    center(f"{t.facility} {t.gender}", F_TITLE, 22)
    center(ISSUE_TYPES[t.issue_type], F_LABEL, 26)
    center(str(t.number), F_NUM, 26)
    if FACILITIES[t.facility] and t.ticket_id:
        q = make_qr(t.ticket_id)
        img.paste(q, (cx - q.width // 2, y))
        y += q.height + 24
    for line in info_lines(t):
        box = d.textbbox((0, 0), line, font=F_INFO)
        d.text((left + 14, y - box[1]), line, font=F_INFO, fill=0)
        y += 36
    y += 10
    center(NOTICE, F_NOTE, 18)
    center(CENTER_NAME, F_ORG, 18)
    d.rectangle((left, PAD, right - 1, y), outline=0, width=BORDER)
    return img.crop((0, 0, WIDTH, y + PAD)).point(lambda v: 0 if v < 128 else 255, "1")
