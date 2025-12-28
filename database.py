import os
import json
import sqlite3
from datetime import datetime, timezone

# Статуси (БЕЗ "Чернетка")
STATUS_ACTIVE = "ACTIVE"    # 🟢 Актуально
STATUS_RESERVE = "RESERVE"  # 🟡 Резерв
STATUS_REMOVED = "REMOVED"  # ⚫️ Знято
STATUS_CLOSED = "CLOSED"    # ✅ Угода закрита

ALL_STATUSES = [STATUS_ACTIVE, STATUS_RESERVE, STATUS_REMOVED, STATUS_CLOSED]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir_for_db(db_path: str) -> None:
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)


class DB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        ensure_dir_for_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            num INTEGER UNIQUE NOT NULL,
            creator_id INTEGER NOT NULL,
            creator_username TEXT,
            broker_username TEXT,
            status TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            photos_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            published_at TEXT,
            group_control_msg_id INTEGER,
            group_album_first_msg_id INTEGER
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            offer_num INTEGER NOT NULL,
            broker_username TEXT,
            status TEXT NOT NULL,
            at TEXT NOT NULL
        );
        """)
        self.conn.commit()

    def _next_num(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COALESCE(MAX(num), 0) + 1 AS n FROM offers;")
        return int(cur.fetchone()["n"])

    def create_offer(self, creator_id: int, creator_username: str, broker_username: str, fields: dict) -> dict:
        num = self._next_num()
        now = utc_now_iso()
        cur = self.conn.cursor()

        # Статус одразу ACTIVE (без Чернетки), але published_at = NULL => ще не в групі
        cur.execute("""
            INSERT INTO offers (num, creator_id, creator_username, broker_username, status, fields_json, photos_json, created_at, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            num, creator_id, creator_username, broker_username,
            STATUS_ACTIVE,
            json.dumps(fields, ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            now
        ))
        offer_id = cur.lastrowid

        # Лог першого статусу (важливо для статистики)
        cur.execute("""
            INSERT INTO status_log (offer_id, offer_num, broker_username, status, at)
            VALUES (?, ?, ?, ?, ?)
        """, (offer_id, num, broker_username, STATUS_ACTIVE, now))

        self.conn.commit()
        return self.get_offer(offer_id)

    def get_offer(self, offer_id: int) -> dict | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM offers WHERE id = ?;", (offer_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_offer_by_num(self, num: int) -> dict | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM offers WHERE num = ?;", (num,))
        row = cur.fetchone()
        return dict(row) if row else None

    def add_photo(self, offer_id: int, file_id: str) -> int:
        offer = self.get_offer(offer_id)
        photos = json.loads(offer["photos_json"])
        photos.append(file_id)
        cur = self.conn.cursor()
        cur.execute("UPDATE offers SET photos_json = ? WHERE id = ?;", (json.dumps(photos, ensure_ascii=False), offer_id))
        self.conn.commit()
        return len(photos)

    def update_field(self, offer_id: int, key: str, value: str) -> None:
        offer = self.get_offer(offer_id)
        fields = json.loads(offer["fields_json"])
        fields[key] = value
        cur = self.conn.cursor()
        cur.execute("UPDATE offers SET fields_json = ? WHERE id = ?;", (json.dumps(fields, ensure_ascii=False), offer_id))
        self.conn.commit()

    def set_broker(self, offer_id: int, broker_username: str) -> None:
        cur = self.conn.cursor()
        cur.execute("UPDATE offers SET broker_username = ? WHERE id = ?;", (broker_username, offer_id))
        self.conn.commit()

    def set_status(self, offer_id: int, status: str) -> None:
        if status not in ALL_STATUSES:
            raise ValueError("Bad status")
        offer = self.get_offer(offer_id)
        now = utc_now_iso()

        cur = self.conn.cursor()
        cur.execute("UPDATE offers SET status = ? WHERE id = ?;", (status, offer_id))
        cur.execute("""
            INSERT INTO status_log (offer_id, offer_num, broker_username, status, at)
            VALUES (?, ?, ?, ?, ?)
        """, (offer_id, offer["num"], offer["broker_username"], status, now))

        self.conn.commit()

    def set_published(self, offer_id: int, group_control_msg_id: int, group_album_first_msg_id: int):
        now = utc_now_iso()
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE offers
            SET published_at = ?, group_control_msg_id = ?, group_album_first_msg_id = ?
            WHERE id = ?;
        """, (now, group_control_msg_id, group_album_first_msg_id, offer_id))
        self.conn.commit()

    def is_published(self, offer_id: int) -> bool:
        offer = self.get_offer(offer_id)
        return bool(offer and offer.get("published_at"))

    # ---------- STATISTICS ----------
    def stats_status_changes(self, start_iso: str, end_iso: str) -> dict:
        """
        Повертає:
        - totals_by_status: {STATUS: count} (скільки разів ставили статуси в період)
        - by_broker: {broker: {STATUS: count}}
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT broker_username, status, COUNT(*) as c
            FROM status_log
            WHERE at >= ? AND at < ?
            GROUP BY broker_username, status
        """, (start_iso, end_iso))
        rows = cur.fetchall()

        totals = {s: 0 for s in ALL_STATUSES}
        by_broker: dict[str, dict] = {}

        for r in rows:
            broker = (r["broker_username"] or "—")
            st = r["status"]
            c = int(r["c"])
            if st in totals:
                totals[st] += c
            if broker not in by_broker:
                by_broker[broker] = {s: 0 for s in ALL_STATUSES}
            if st in by_broker[broker]:
                by_broker[broker][st] += c

        return {"totals_by_status": totals, "by_broker": by_broker}

    def stats_current_offers(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT status, COUNT(*) as c FROM offers GROUP BY status;")
        rows = cur.fetchall()
        out = {s: 0 for s in ALL_STATUSES}
        for r in rows:
            st = r["status"]
            if st in out:
                out[st] = int(r["c"])
        return out
