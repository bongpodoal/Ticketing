"""Flask 발권 서버.  실행: python app.py  ->  http://127.0.0.1:5000"""
import hmac
import io
import os
import re
from datetime import datetime
from functools import wraps

from flask import Flask, Response, jsonify, render_template, request, send_file

import database as db
import printer
from receipt import ENTRY_TYPES, FACILITIES, GENDERS, ISSUE_TYPES, Ticket, render

app = Flask(__name__)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ADMIN_PASSWORD = os.environ.get("TICKET_ADMIN_PASSWORD", "")
STATUSES = {"ACTIVE": "정상", "WAITING": "대기"}


def admin_only(view):
    """개인정보 화면 보호: 비밀번호가 설정돼 있으면 HTTP 기본 인증(사용자명 무관),
    없으면 이 PC(localhost)에서 온 요청만 허용."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if ADMIN_PASSWORD:
            auth = request.authorization
            if not (auth and hmac.compare_digest(auth.password or "", ADMIN_PASSWORD)):
                return Response("관리자 인증이 필요합니다.", 401, {"WWW-Authenticate": 'Basic realm="admin"'})
        elif request.remote_addr not in ("127.0.0.1", "::1"):
            return Response("관리 페이지는 발권 PC에서만 열 수 있습니다. (TICKET_ADMIN_PASSWORD 설정 시 원격 허용)", 403)
        return view(*args, **kwargs)

    return wrapper


class InputError(ValueError):
    pass


def parse_form(f: dict) -> Ticket:
    """입력값 검사 후 Ticket 생성 (ticket_id, 대기번호는 아직 비어 있음)."""

    def pick(key, allowed):
        v = str(f.get(key, "")).strip()
        if v not in allowed:
            raise InputError(f"{key} 값이 올바르지 않습니다: {v!r}")
        return v

    def positive_int(key, label):
        try:
            v = int(str(f.get(key, "")).strip())
        except ValueError:
            raise InputError(f"{label}를 숫자로 입력하세요.") from None
        if v < 0:
            raise InputError(f"{label}는 0 이상이어야 합니다.")
        return v

    t = Ticket(
        entry_type=pick("entry_type", ENTRY_TYPES),
        facility=pick("facility", FACILITIES),
        gender=pick("gender", GENDERS),
        issue_type=pick("issue_type", ISSUE_TYPES),
        number=0,
    )
    if t.issue_type == "normal":
        t.number = positive_int("locker", "락카번호")
    if t.entry_type == "member":
        t.member_id = str(f.get("member_id", "")).strip()
        t.member_name = str(f.get("member_name", "")).strip()
        t.start_date = str(f.get("start_date", "")).strip()
        t.end_date = str(f.get("end_date", "")).strip()
        if not t.member_id or not t.member_name:
            raise InputError("회원번호와 회원명을 입력하세요.")
        if not (DATE_RE.match(t.start_date) and DATE_RE.match(t.end_date)):
            raise InputError("이용기간을 YYYY-MM-DD 형식으로 입력하세요.")
        if t.start_date > t.end_date:
            raise InputError("이용 종료일이 시작일보다 빠릅니다.")
    else:
        t.fee = positive_int("fee", "이용료")
    return t


@app.errorhandler(InputError)
def input_error(e):
    return jsonify(ok=False, error=str(e)), 400


@app.get("/")
def index():
    return render_template(
        "index.html", facilities=list(FACILITIES), genders=GENDERS, today=f"{datetime.now():%Y-%m-%d}"
    )


@app.post("/api/tickets")
def create_ticket():
    t = parse_form(request.get_json(force=True))
    t.printed_at = datetime.now()
    conn = db.connect()
    try:
        with conn:  # 인쇄 실패 시 발권 기록도 롤백
            t.ticket_id = db.next_ticket_id(conn, t.printed_at)
            if t.issue_type == "waiting":
                t.number = db.next_waiting_no(conn, t.printed_at, t.facility, t.gender)
            if t.entry_type == "member":
                db.upsert_member(conn, t.member_id, t.member_name, t.start_date, t.end_date)
            db.insert_ticket(
                conn,
                ticket_id=t.ticket_id,
                member_id=t.member_id or None,
                entry_type=t.entry_type,
                facility=t.facility,
                gender=t.gender,
                issue_type=t.issue_type,
                locker=t.number if t.issue_type == "normal" else None,
                waiting_no=t.number if t.issue_type == "waiting" else None,
                fee=t.fee if t.entry_type == "daily" else None,
                printed_at=f"{t.printed_at:%Y-%m-%d %H:%M:%S}",
                status="WAITING" if t.issue_type == "waiting" else "ACTIVE",
            )
            printer.print_images([render(t)], t.ticket_id)
    except Exception as e:  # noqa: BLE001 - 프린터 오류를 화면에 그대로 보여줌
        app.logger.exception("발권 실패")
        return jsonify(ok=False, error=f"출력 실패: {e}"), 500
    finally:
        conn.close()
    return jsonify(ok=True, ticket_id=t.ticket_id, number=t.number, issue_type=t.issue_type)


@app.post("/api/preview")
def preview():
    """DB 기록·인쇄 없이 영수증 이미지만 확인."""
    t = parse_form(request.get_json(force=True))
    t.ticket_id = "TICKET-PREVIEW"
    if t.issue_type == "waiting":
        conn = db.connect()
        try:
            t.number = db.next_waiting_no(conn, t.printed_at, t.facility, t.gender)
        finally:
            conn.close()
    buf = io.BytesIO()
    render(t).save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.get("/api/tickets/<ticket_id>")
@admin_only
def ticket_status(ticket_id):
    """QR 스캔 시 발권 상태 조회."""
    row = db.get_ticket(ticket_id)
    if not row:
        return jsonify(ok=False, error="발권 기록이 없습니다."), 404
    return jsonify(ok=True, ticket=row)


@app.get("/admin")
@admin_only
def admin():
    view = request.args.get("view", "tickets")
    today = f"{datetime.now():%Y-%m-%d}"
    date = request.args.get("date", today)  # 빈 문자열이면 전체 기간
    if date and not DATE_RE.match(date):
        date = today
    facility = request.args.get("facility", "")
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    ctx = dict(
        view=view, date=date, today=today, facility=facility, status=status, q=q,
        facilities=list(FACILITIES), statuses=STATUSES, entry_types=ENTRY_TYPES,
        db_path=db.DB_PATH, summary=db.ticket_summary(date or today),
    )
    if view == "members":
        ctx["members"] = db.list_members(q)
    else:
        ctx["tickets"] = db.search_tickets(date, facility, status, q)
    return render_template("admin.html", **ctx)


db.init_db()

if __name__ == "__main__":
    app.run(host=os.environ.get("TICKET_HOST", "127.0.0.1"), port=int(os.environ.get("TICKET_PORT", 5000)))
