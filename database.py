import json
import aiosqlite
from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple

STATUS_ACTIVE = "active"
STATUS_RESERVED = "reserved"
STATUS_CLOSED = "closed"
STATUS_REMOVED = "removed"


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


async def init_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            broker TEXT,
            status TEXT NOT NULL,
            category TEXT,
            living_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            price TEXT,
            deposit TEXT,
            commission TEXT,
            parking TEXT,
            move_in TEXT,
            viewings TEXT,
            photos_json TEXT,
            group_chat_id INTEGER,
            group_message_id INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT,
            changed_at TEXT NOT NULL,
            FOREIGN KEY(offer_id) REFERENCES offers(id)
        )
        """)
        await db.commit()


async def create_offer(db_path: str, data: Dict[str, Any]) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("""
        INSERT INTO offers (
            created_at, broker, status, category, living_type, street, city, district,
            advantages, price, deposit, commission, parking, move_in, viewings, photos_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso(),
            data.get("broker"),
            data.get("status"),
            data.get("category"),
            data.get("living_type"),
            data.get("street"),
            data.get("city"),
            data.get("district"),
            data.get("advantages"),
            data.get("price"),
            data.get("deposit"),
            data.get("commission"),
            data.get("parking"),
            data.get("move_in"),
            data.get("viewings"),
            json.dumps(data.get("photos", []), ensure_ascii=False),
        ))
        await db.commit()
        return cur.lastrowid


async def set_group_message(db_path: str, offer_id: int, chat_id: int, message_id: int):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
        UPDATE offers SET group_chat_id=?, group_message_id=? WHERE id=?
        """, (chat_id, message_id, offer_id))
        await db.commit()


async def get_offer(db_path: str, offer_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
        row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["photos"] = json.loads(d.get("photos_json") or "[]")
        return d


async def update_offer_fields(db_path: str, offer_id: int, fields: Dict[str, Any]):
    keys = []
    vals = []
    for k, v in fields.items():
        keys.append(f"{k}=?")
        vals.append(v)
    if not keys:
        return
    vals.append(offer_id)
    q = f"UPDATE offers SET {', '.join(keys)} WHERE id=?"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(q, tuple(vals))
        await db.commit()


async def change_status(db_path: str, offer_id: int, new_status: str, changed_by: str):
    offer = await get_offer(db_path, offer_id)
    if not offer:
        return
    old_status = offer["status"]
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id))
        await db.execute("""
        INSERT INTO status_log (offer_id, old_status, new_status, changed_by, changed_at)
        VALUES (?, ?, ?, ?, ?)
        """, (offer_id, old_status, new_status, changed_by, now_iso()))
        await db.commit()


def _day_range(d: date) -> Tuple[str, str]:
    start = datetime(d.year, d.month, d.day, 0, 0, 0)
    end = datetime(d.year, d.month, d.day, 23, 59, 59)
    return (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))


def _month_range(d: date) -> Tuple[str, str]:
    start = datetime(d.year, d.month, 1, 0, 0, 0)
    if d.month == 12:
        end = datetime(d.year + 1, 1, 1, 0, 0, 0)
    else:
        end = datetime(d.year, d.month + 1, 1, 0, 0, 0)
    # end exclusive, але ок
    return (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))


def _year_range(d: date) -> Tuple[str, str]:
    start = datetime(d.year, 1, 1, 0, 0, 0)
    end = datetime(d.year + 1, 1, 1, 0, 0, 0)
    return (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))


async def stats_counts_by_status(db_path: str, start_iso: str, end_iso: str) -> Dict[str, int]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("""
        SELECT status, COUNT(*) as c
        FROM offers
        WHERE created_at >= ? AND created_at < ?
        GROUP BY status
        """, (start_iso, end_iso))
        rows = await cur.fetchall()
        out = {STATUS_ACTIVE: 0, STATUS_RESERVED: 0, STATUS_CLOSED: 0, STATUS_REMOVED: 0}
        for status, c in rows:
            out[status] = c
        return out


async def broker_status_changes(db_path: str, start_iso: str, end_iso: str) -> Dict[str, Dict[str, int]]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("""
        SELECT changed_by, new_status, COUNT(*) as c
        FROM status_log
        WHERE changed_at >= ? AND changed_at < ?
        GROUP BY changed_by, new_status
        """, (start_iso, end_iso))
        rows = await cur.fetchall()
        result: Dict[str, Dict[str, int]] = {}
        for changed_by, new_status, c in rows:
            broker = changed_by or "—"
            if broker not in result:
                result[broker] = {STATUS_ACTIVE: 0, STATUS_RESERVED: 0, STATUS_CLOSED: 0, STATUS_REMOVED: 0}
            result[broker][new_status] = c
        return result


async def build_stats_text(db_path: str, today: date) -> str:
    d1s, d1e = _day_range(today)
    ms, me = _month_range(today)
    ys, ye = _year_range(today)

    day_counts = await stats_counts_by_status(db_path, d1s, d1e)
    month_counts = await stats_counts_by_status(db_path, ms, me)
    year_counts = await stats_counts_by_status(db_path, ys, ye)

    day_b = await broker_status_changes(db_path, d1s, d1e)
    month_b = await broker_status_changes(db_path, ms, me)
    year_b = await broker_status_changes(db_path, ys, ye)

    def fmt_counts(title: str, counts: Dict[str, int]) -> str:
        return (
            f"<b>{title}</b>\n"
            f"🟢 Актуально: <b>{counts[STATUS_ACTIVE]}</b>\n"
            f"🟡 Резерв: <b>{counts[STATUS_RESERVED]}</b>\n"
            f"✅ Закрито: <b>{counts[STATUS_CLOSED]}</b>\n"
            f"🔴 Знято: <b>{counts[STATUS_REMOVED]}</b>\n"
        )

    def fmt_brokers(title: str, data: Dict[str, Dict[str, int]]) -> str:
        lines = [f"<b>{title}</b>"]
        if not data:
            lines.append("— немає змін статусів")
            return "\n".join(lines) + "\n"
        for broker, c in sorted(data.items(), key=lambda x: x[0].lower()):
            lines.append(
                f"👤 <b>{broker}</b>  |  "
                f"🟢 {c[STATUS_ACTIVE]}  "
                f"🟡 {c[STATUS_RESERVED]}  "
                f"✅ {c[STATUS_CLOSED]}  "
                f"🔴 {c[STATUS_REMOVED]}"
            )
        return "\n".join(lines) + "\n"

    text = (
        "📊 <b>Статистика</b>\n\n"
        + fmt_counts(f"День ({today.isoformat()})", day_counts) + "\n"
        + fmt_counts(f"Місяць ({today.strftime('%Y-%m')})", month_counts) + "\n"
        + fmt_counts(f"Рік ({today.strftime('%Y')})", year_counts) + "\n"
        + "🧾 <b>Хто скільки змінив статусів</b>\n\n"
        + fmt_brokers(f"День ({today.isoformat()})", day_b) + "\n"
        + fmt_brokers(f"Місяць ({today.strftime('%Y-%m')})", month_b) + "\n"
        + fmt_brokers(f"Рік ({today.strftime('%Y')})", year_b)
    )
    return text
