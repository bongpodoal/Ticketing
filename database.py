"""SQLite: 회원 / 발권 기록, 발권번호·대기번호 발급."""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get(
    "TICKET_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipt.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    member_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   TEXT PRIMARY KEY,          -- TICKET-YYYYMMDD-000001
    member_id   TEXT REFERENCES members(member_id),
    entry_type  TEXT NOT NULL,             -- member | daily
    facility    TEXT NOT NULL,
    gender      TEXT NOT NULL,
    issue_type  TEXT NOT NULL,             -- normal | waiting
    locker      INTEGER,
    waiting_no  INTEGER,
    fee         INTEGER,
    printed_at  TEXT NOT NULL,             -- YYYY-MM-DD HH:MM:SS
    status      TEXT NOT NULL              -- ACTIVE | WAITING
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_member(conn, member_id, name, start_date, end_date):
    conn.execute(
        "INSERT INTO members VALUES (?, ?, ?, ?) ON CONFLICT(member_id) DO UPDATE SET "
        "name=excluded.name, start_date=excluded.start_date, end_date=excluded.end_date",
        (member_id, name, start_date, end_date),
    )


def next_ticket_id(conn, now: datetime) -> str:
    prefix = f"TICKET-{now:%Y%m%d}-"
    row = conn.execute(
        "SELECT ticket_id FROM tickets WHERE ticket_id LIKE ? ORDER BY ticket_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    seq = int(row["ticket_id"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}{seq:06d}"


def next_waiting_no(conn, now: datetime, facility: str, gender: str) -> int:
    """당일, 같은 시설·성별 안에서 1부터 증가."""
    row = conn.execute(
        "SELECT MAX(waiting_no) FROM tickets WHERE issue_type='waiting' "
        "AND facility=? AND gender=? AND printed_at LIKE ?",
        (facility, gender, f"{now:%Y-%m-%d}%"),
    ).fetchone()
    return (row[0] or 0) + 1


def insert_ticket(conn, **t):
    conn.execute(
        "INSERT INTO tickets (ticket_id, member_id, entry_type, facility, gender, issue_type, "
        "locker, waiting_no, fee, printed_at, status) VALUES "
        "(:ticket_id, :member_id, :entry_type, :facility, :gender, :issue_type, "
        ":locker, :waiting_no, :fee, :printed_at, :status)",
        t,
    )


def get_ticket(ticket_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT t.*, m.name AS member_name, m.start_date, m.end_date FROM tickets t "
            "LEFT JOIN members m USING (member_id) WHERE ticket_id=?",
            (ticket_id,),
        ).fetchone()
    return dict(row) if row else None


def search_tickets(date="", facility="", status="", q="", limit=500):
    """관리 페이지용 발권 목록 (최신순). 빈 값은 필터 미적용."""
    where, args = [], []
    if date:
        where.append("t.printed_at LIKE ?")
        args.append(f"{date}%")
    if facility:
        where.append("t.facility = ?")
        args.append(facility)
    if status:
        where.append("t.status = ?")
        args.append(status)
    if q:
        where.append("(t.ticket_id LIKE ? OR t.member_id LIKE ? OR m.name LIKE ?)")
        args += [f"%{q}%"] * 3
    sql = (
        "SELECT t.*, m.name AS member_name FROM tickets t LEFT JOIN members m USING (member_id)"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY t.printed_at DESC, t.ticket_id DESC LIMIT ?"
    )
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, (*args, limit))]


def ticket_summary(date):
    """해당 날짜의 전체 / 상태별 발권 수와 일일 이용료 합계."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n, COALESCE(SUM(fee), 0) AS fee FROM tickets "
            "WHERE printed_at LIKE ? GROUP BY status",
            (f"{date}%",),
        ).fetchall()
    total = {"count": 0, "ACTIVE": 0, "WAITING": 0, "fee": 0}
    for r in rows:
        total["count"] += r["n"]
        total[r["status"]] = total.get(r["status"], 0) + r["n"]
        total["fee"] += r["fee"]
    return total


def list_members(q=""):
    """회원 목록 + 마지막 발권 시각, 발권 횟수."""
    sql = (
        "SELECT m.*, COUNT(t.ticket_id) AS ticket_count, MAX(t.printed_at) AS last_printed "
        "FROM members m LEFT JOIN tickets t USING (member_id) "
        "WHERE m.member_id LIKE ? OR m.name LIKE ? "
        "GROUP BY m.member_id ORDER BY last_printed DESC"
    )
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, (f"%{q}%", f"%{q}%"))]
