#!/usr/bin/env python3
"""docs/영수증 출력 양식.pdf 의 예시 6장을 출력한다 (DB 기록 없음).

python tools/print_samples.py            # 인쇄
python tools/print_samples.py --preview  # output/samples_preview.png 만 생성
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image  # noqa: E402

import printer  # noqa: E402
from receipt import WIDTH, Ticket, render  # noqa: E402

AT = datetime(2026, 6, 21, 14, 16)
MEMBER = dict(entry_type="member", member_id="99014804", member_name="이상재",
              start_date="2026-06-04", end_date="2026-07-03", printed_at=AT)
DAILY = dict(entry_type="daily", printed_at=AT)

SAMPLES = [
    Ticket(facility="헬스1", gender="남자", issue_type="normal", number=150, ticket_id="TICKET-SAMPLE-1", **MEMBER),
    Ticket(facility="헬스2", gender="여자", issue_type="normal", number=36, ticket_id="TICKET-SAMPLE-2", fee=2500, **DAILY),
    Ticket(facility="헬스1", gender="남자", issue_type="waiting", number=1, ticket_id="TICKET-SAMPLE-3", **MEMBER),
    Ticket(facility="헬스2", gender="여자", issue_type="waiting", number=2, ticket_id="TICKET-SAMPLE-4", fee=2500, **DAILY),
    Ticket(facility="수영", gender="남자", issue_type="normal", number=150, ticket_id="TICKET-SAMPLE-5", **MEMBER),
    Ticket(facility="수영", gender="여자", issue_type="normal", number=36, ticket_id="TICKET-SAMPLE-6", fee=3500, **DAILY),
]


def main():
    imgs = [render(t) for t in SAMPLES]
    if "--preview" not in sys.argv:
        printer.print_images(imgs, "sample")
        return
    row_h = max(i.height for i in imgs) + 20
    sheet = Image.new("L", (WIDTH * 3 + 40, row_h * 2), 200)
    for n, im in enumerate(imgs):
        sheet.paste(im.convert("L"), ((n % 3) * (WIDTH + 20), (n // 3) * row_h))
    os.makedirs(printer.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(printer.OUTPUT_DIR, "samples_preview.png")
    sheet.save(path)
    print(path)


if __name__ == "__main__":
    main()
