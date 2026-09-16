"""관리 페이지: 로그인, 발권·회원 조회 및 수정, 비밀번호 변경."""
import hmac
import secrets
import sqlite3
import time
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

import database as db
from receipt import ENTRY_TYPES, FACILITIES, GENDERS

bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUSES = {"ACTIVE": "정상", "WAITING": "대기"}
LOCAL_ADDRS = ("127.0.0.1", "::1")


class FormError(ValueError):
    pass


def login_required(view):
    """로그인한 관리자만 허용. 초기 비밀번호(admin)를 쓰는 동안에는 이 PC에서만 접속 가능."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = session.get("admin")
        if not user:
            return redirect(url_for("admin.login", next=request.full_path))
        if db.is_default_password(user) and request.remote_addr not in LOCAL_ADDRS:
            abort(403, "초기 비밀번호를 변경하기 전에는 발권 PC에서만 관리 페이지를 열 수 있습니다.")
        return view(*args, **kwargs)

    return wrapper


@bp.before_request
def check_csrf():
    if request.method == "POST" and request.endpoint != "admin.login":
        token = request.form.get("csrf_token", "")
        if not hmac.compare_digest(token, session.get("csrf_token", "")):
            abort(400, "요청이 만료되었습니다. 페이지를 새로고침한 뒤 다시 시도하세요.")


@bp.app_context_processor
def inject_admin():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    user = session.get("admin")
    return dict(
        csrf_token=session["csrf_token"],
        admin_user=user,
        default_password=bool(user) and db.is_default_password(user),
    )


def _safe_next(target):
    return target if target and target.startswith("/admin") and not target.startswith("//") else url_for("admin.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if db.check_admin(username, password):
            session.clear()
            session["admin"] = username
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(_safe_next(request.args.get("next")))
        time.sleep(1)  # 무차별 대입 속도 늦추기
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("admin_login.html", error=error)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        user = session["admin"]
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        if not db.check_admin(user, current):
            flash("현재 비밀번호가 올바르지 않습니다.", "error")
        elif len(new) < 8:
            flash("새 비밀번호는 8자 이상이어야 합니다.", "error")
        elif new != request.form.get("confirm", ""):
            flash("새 비밀번호 확인이 일치하지 않습니다.", "error")
        elif new == current:
            flash("현재 비밀번호와 다른 비밀번호를 입력하세요.", "error")
        else:
            db.set_admin_password(user, new)
            flash("비밀번호를 변경했습니다.", "ok")
            return redirect(url_for("admin.index"))
    return render_template("admin_password.html")


# ---- 조회 ----

@bp.get("")
@login_required
def index():
    view = request.args.get("view", "tickets")
    today = f"{datetime.now():%Y-%m-%d}"
    date = request.args.get("date", today)  # 빈 문자열이면 전체 기간
    if date and not _is_date(date):
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


# ---- 발권 기록 수정 ----

def _is_date(v):
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _opt_int(form, key, label):
    v = form.get(key, "").strip()
    if not v:
        return None
    if not v.isdigit():
        raise FormError(f"{label}는 0 이상의 숫자로 입력하세요.")
    return int(v)


def _ticket_form(form, ticket):
    f = dict(
        facility=form.get("facility", ""),
        gender=form.get("gender", ""),
        status=form.get("status", ""),
        locker=_opt_int(form, "locker", "락카번호"),
        waiting_no=_opt_int(form, "waiting_no", "대기번호"),
        fee=_opt_int(form, "fee", "이용료"),
        member_id=form.get("member_id", "").strip() or None,
    )
    if f["facility"] not in FACILITIES or f["gender"] not in GENDERS or f["status"] not in STATUSES:
        raise FormError("시설·성별·상태 값이 올바르지 않습니다.")
    if f["status"] == "ACTIVE" and f["locker"] is None:
        raise FormError("정상 상태로 바꾸려면 락카번호를 입력하세요.")
    if ticket["entry_type"] == "member":
        if not f["member_id"]:
            raise FormError("회원입장 기록에는 회원번호가 필요합니다.")
        if not db.get_member(f["member_id"]):
            raise FormError(f"회원번호 {f['member_id']}가 회원 목록에 없습니다. 회원을 먼저 등록하세요.")
        f["fee"] = None
    else:
        f["member_id"] = None
        if f["fee"] is None:
            raise FormError("일일입장 기록에는 이용료가 필요합니다.")
    return f


@bp.route("/tickets/<ticket_id>", methods=["GET", "POST"])
@login_required
def edit_ticket(ticket_id):
    ticket = db.get_ticket(ticket_id) or abort(404)
    back = _safe_next(request.args.get("next"))
    if request.method == "POST":
        try:
            fields = _ticket_form(request.form, ticket)
        except FormError as e:
            flash(str(e), "error")
            ticket.update({k: request.form.get(k, "") for k in db.TICKET_EDITABLE})
        else:
            db.update_ticket(ticket_id, **fields)
            flash(f"{ticket_id} 기록을 수정했습니다.", "ok")
            return redirect(back)
    return render_template(
        "admin_ticket.html", t=ticket, back=back, facilities=list(FACILITIES), genders=GENDERS,
        statuses=STATUSES, entry_types=ENTRY_TYPES,
    )


@bp.post("/tickets/<ticket_id>/delete")
@login_required
def delete_ticket(ticket_id):
    db.get_ticket(ticket_id) or abort(404)
    db.delete_ticket(ticket_id)
    flash(f"{ticket_id} 기록을 삭제했습니다.", "ok")
    return redirect(_safe_next(request.args.get("next")))


# ---- 회원 수정 ----

def _member_form(form):
    name = form.get("name", "").strip()
    start, end = form.get("start_date", ""), form.get("end_date", "")
    if not name:
        raise FormError("회원명을 입력하세요.")
    if not (_is_date(start) and _is_date(end)):
        raise FormError("이용기간을 입력하세요.")
    if start > end:
        raise FormError("이용 종료일이 시작일보다 빠릅니다.")
    return name, start, end


@bp.route("/members/new", methods=["GET", "POST"])
@login_required
def new_member():
    m = dict(member_id="", name="", start_date="", end_date="", ticket_count=0)
    if request.method == "POST":
        m.update({k: request.form.get(k, "").strip() for k in ("member_id", "name", "start_date", "end_date")})
        try:
            if not m["member_id"]:
                raise FormError("회원번호를 입력하세요.")
            db.insert_member(m["member_id"], *_member_form(request.form))
        except FormError as e:
            flash(str(e), "error")
        except sqlite3.IntegrityError:
            flash(f"회원번호 {m['member_id']}는 이미 등록돼 있습니다.", "error")
        else:
            flash(f"회원 {m['member_id']}를 등록했습니다.", "ok")
            return redirect(url_for("admin.index", view="members"))
    return render_template("admin_member.html", m=m, is_new=True)


@bp.route("/members/<member_id>", methods=["GET", "POST"])
@login_required
def edit_member(member_id):
    m = db.get_member(member_id) or abort(404)
    if request.method == "POST":
        try:
            db.update_member(member_id, *_member_form(request.form))
        except FormError as e:
            flash(str(e), "error")
            m.update({k: request.form.get(k, "") for k in ("name", "start_date", "end_date")})
        else:
            flash(f"회원 {member_id} 정보를 수정했습니다.", "ok")
            return redirect(url_for("admin.index", view="members"))
    return render_template("admin_member.html", m=m, is_new=False)


@bp.post("/members/<member_id>/delete")
@login_required
def delete_member(member_id):
    db.get_member(member_id) or abort(404)
    if db.delete_member(member_id):
        flash(f"회원 {member_id}를 삭제했습니다.", "ok")
    else:
        flash("발권 기록이 남아 있는 회원은 삭제할 수 없습니다. 발권 기록을 먼저 삭제하세요.", "error")
    return redirect(url_for("admin.index", view="members"))
