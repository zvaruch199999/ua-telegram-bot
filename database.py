import aiosqlite
from datetime import datetime

STATUS_ACTIVE = "ACTIVE"
STATUS_RESERVED = "RESERVED"
STATUS_REMOVED = "REMOVED"
STATUS_CLOSED = "CLOSED"

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()

class DB:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                created_by_id INTEGER NOT NULL,
                created_by_username TEXT,
                category TEXT,
                housing_type TEXT,
                street TEXT,
                city TEXT,
                district TEXT,
                advantages TEXT,
                rent TEXT,
                deposit TEXT,
                commission TEXT,
                parking TEXT,
                move_in_from TEXT,
                viewings_from TEXT,
                broker TEXT,
                status TEXT NOT NULL,
                group_chat_id INTEGER,
                group_message_id INTEGER
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS offer_photos (
                offer_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                pos INTEGER NOT NULL,
                FOREIGN KEY(offer_id) REFERENCES offers(id)
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                old_status TEXT,
                new_status TEXT,
                FOREIGN KEY(offer_id) REFERENCES offers(id)
            )
            """)
            await db.commit()

    async def create_offer(self, created_by_id: int, created_by_username: str, data: dict) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                INSERT INTO offers (
                    created_at, created_by_id, created_by_username,
                    category, housing_type, street, city, district,
                    advantages, rent, deposit, commission, parking,
                    move_in_from, viewings_from, broker, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                now_iso(), created_by_id, created_by_username,
                data.get("category"), data.get("housing_type"),
                data.get("street"), data.get("city"), data.get("district"),
                data.get("advantages"), data.get("rent"), data.get("deposit"),
                data.get("commission"), data.get("parking"),
                data.get("move_in_from"), data.get("viewings_from"),
                data.get("broker"), STATUS_ACTIVE
            ))
            await db.commit()
            return cur.lastrowid

    async def set_photos(self, offer_id: int, photos: list[str]):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM offer_photos WHERE offer_id=?", (offer_id,))
            for i, fid in enumerate(photos, start=1):
                await db.execute(
                    "INSERT INTO offer_photos(offer_id,file_id,pos) VALUES (?,?,?)",
                    (offer_id, fid, i)
                )
            await db.commit()

    async def get_photos(self, offer_id: int) -> list[str]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT file_id FROM offer_photos WHERE offer_id=? ORDER BY pos ASC",
                (offer_id,)
            )
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def get_offer(self, offer_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    async def update_offer_field(self, offer_id: int, field: str, value: str):
        if field not in {
            "category","housing_type","street","city","district","advantages",
            "rent","deposit","commission","parking","move_in_from","viewings_from","broker"
        }:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE offers SET {field}=? WHERE id=?", (value, offer_id))
            await db.commit()

    async def set_group_message(self, offer_id: int, group_chat_id: int, group_message_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE offers SET group_chat_id=?, group_message_id=? WHERE id=?",
                (group_chat_id, group_message_id, offer_id)
            )
            await db.commit()

    async def change_status(self, offer_id: int, user_id: int, username: str, new_status: str):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT status FROM offers WHERE id=?", (offer_id,))
            row = await cur.fetchone()
            if not row:
                return None
            old = row[0]
            await db.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id))
            await db.execute("""
                INSERT INTO status_log(offer_id, ts, user_id, username, old_status, new_status)
                VALUES (?,?,?,?,?,?)
            """, (offer_id, now_iso(), user_id, username, old, new_status))
            await db.commit()
            return old

    async def stats_counts(self, date_from: str, date_to: str) -> dict:
        # counts по статусам за період (по логах)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT new_status, COUNT(*)
                FROM status_log
                WHERE ts >= ? AND ts < ?
                GROUP BY new_status
            """, (date_from, date_to))
            rows = await cur.fetchall()
            return {k: v for k, v in rows}

    async def stats_by_broker_status(self, date_from: str, date_to: str) -> dict:
        # username -> {status -> count}
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT COALESCE(username,'(no_username)') as u, new_status, COUNT(*)
                FROM status_log
                WHERE ts >= ? AND ts < ?
                GROUP BY u, new_status
                ORDER BY u
            """, (date_from, date_to))
            rows = await cur.fetchall()
            out = {}
            for u, st, c in rows:
                out.setdefault(u, {})[st] = c
            return out
