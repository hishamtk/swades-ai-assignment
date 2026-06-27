"""SQLite-backed appointment booking with simple weekly slots."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "appointments.db"

# Mon–Fri, 9:00–17:00, 30-minute slots
WORK_DAYS = {0, 1, 2, 3, 4}
DAY_START = time(9, 0)
DAY_END = time(17, 0)
SLOT_MINUTES = 30


@dataclass
class Appointment:
    id: int
    name: str
    reason: str
    slot: datetime
    phone: str


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                reason TEXT NOT NULL,
                slot TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def parse_preferred_date(value: str) -> date:
    """Parse a caller-provided date string."""
    return _parse_date(value)


def is_clinic_open(day: date) -> bool:
    return day.weekday() in WORK_DAYS


def _infer_year(month: int, day: int, *, today: date | None = None) -> int:
    """Pick the next calendar year for a month/day on or after today."""
    today = today or date.today()
    candidate = date(today.year, month, day)
    if candidate >= today:
        return today.year
    return today.year + 1


def _normalize_booking_date(day: date) -> date:
    """If the LLM passes a past year (e.g. 2024), remap to the next valid occurrence."""
    today = date.today()
    if day >= today:
        return day
    try:
        candidate = day.replace(year=today.year)
        if candidate >= today:
            return candidate
        return day.replace(year=today.year + 1)
    except ValueError:
        return day


def _parse_date(value: str) -> date:
    cleaned = value.strip()
    today = date.today()

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return _normalize_booking_date(datetime.strptime(cleaned, fmt).date())
        except ValueError:
            continue

    for fmt in ("%B %d", "%b %d", "%m/%d"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            year = _infer_year(parsed.month, parsed.day, today=today)
            return date(year, parsed.month, parsed.day)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {value}")


def _parse_datetime(value: str) -> datetime:
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %I:%M %p",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse datetime: {value}")


def _iter_slots(day: date) -> list[datetime]:
    if day.weekday() not in WORK_DAYS:
        return []
    slots: list[datetime] = []
    cursor = datetime.combine(day, DAY_START)
    end = datetime.combine(day, DAY_END)
    delta = timedelta(minutes=SLOT_MINUTES)
    while cursor < end:
        slots.append(cursor)
        cursor += delta
    return slots


def _booked_slots(conn: sqlite3.Connection, day: date) -> set[str]:
    prefix = day.isoformat()
    rows = conn.execute(
        "SELECT slot FROM appointments WHERE slot LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    return {row["slot"] for row in rows}


def get_available_slots(preferred_date: str) -> list[str]:
    """Return ISO datetime strings for open slots on the given date."""
    init_db()
    day = _parse_date(preferred_date)
    today = date.today()
    if day < today:
        return []

    with _connect() as conn:
        booked = _booked_slots(conn, day)
        available = [
            slot.isoformat(timespec="minutes")
            for slot in _iter_slots(day)
            if slot.isoformat(timespec="minutes") not in booked
            and (day > today or slot > datetime.now())
        ]
    return available


def availability_message(preferred_date: str) -> str:
    """Human-readable availability result for the agent to speak."""
    try:
        slots = get_available_slots(preferred_date)
    except ValueError as exc:
        return f"Could not understand that date: {exc}. Please ask for a date like 2026-07-15."

    if not slots:
        try:
            day = parse_preferred_date(preferred_date)
            if not is_clinic_open(day):
                return (
                    f"{day.strftime('%A, %B %d')} is a weekend — we're closed. "
                    "Please ask for a weekday (Monday through Friday)."
                )
        except ValueError:
            pass
        return (
            f"No open slots on {preferred_date}. "
            "Suggest another weekday (Monday through Friday, 9 AM to 5 PM)."
        )

    human = [format_slot_human(s) for s in slots[:8]]
    return "Available times: " + "; ".join(human)


def find_booking_by_phone_and_slot(phone: str, slot_datetime: str) -> Appointment | None:
    """Return an existing appointment if this caller already holds the slot."""
    init_db()
    try:
        slot_key = _parse_datetime(slot_datetime).isoformat(timespec="minutes")
    except ValueError:
        return None

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, reason, slot, phone
            FROM appointments
            WHERE slot = ? AND phone = ?
            LIMIT 1
            """,
            (slot_key, phone.strip()),
        ).fetchone()

    if row is None:
        return None

    return Appointment(
        id=row["id"],
        name=row["name"],
        reason=row["reason"],
        slot=_parse_datetime(row["slot"]),
        phone=row["phone"],
    )


def create_booking(
    name: str,
    reason: str,
    slot_datetime: str,
    phone: str,
) -> Appointment:
    init_db()
    slot = _parse_datetime(slot_datetime)
    slot_key = slot.isoformat(timespec="minutes")

    with _connect() as conn:
        if slot_key not in get_available_slots(slot.date().isoformat()):
            raise ValueError("That slot is no longer available.")

        cur = conn.execute(
            """
            INSERT INTO appointments (name, reason, slot, phone)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), reason.strip(), slot_key, phone.strip()),
        )
        conn.commit()
        return Appointment(
            id=cur.lastrowid,
            name=name.strip(),
            reason=reason.strip(),
            slot=slot,
            phone=phone.strip(),
        )


def save_call_summary(room_name: str, summary: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO call_logs (room_name, summary) VALUES (?, ?)",
            (room_name, summary),
        )
        conn.commit()


def get_call_summary(room_name: str) -> dict[str, str] | None:
    """Return the latest saved summary for a room, if any."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT room_name, summary, created_at
            FROM call_logs
            WHERE room_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (room_name,),
        ).fetchone()

    if row is None:
        return None

    return {
        "room_name": row["room_name"],
        "summary": row["summary"],
        "created_at": row["created_at"],
    }


def list_appointments(limit: int = 100) -> list[dict[str, str | int]]:
    """Return booked appointments for the dashboard, newest scheduled first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, reason, slot, phone, created_at
            FROM appointments
            ORDER BY slot DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "reason": row["reason"],
            "slot": row["slot"],
            "slot_display": format_slot_human(row["slot"]),
            "phone": row["phone"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def format_slot_human(slot_iso: str) -> str:
    dt = _parse_datetime(slot_iso)
    return dt.strftime("%A, %B %d at %I:%M %p")
