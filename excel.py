import csv
import os
import aiosqlite

async def export_offers_csv(db_path: str, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("""
            SELECT id, created_at, created_by_username, broker, status,
                   category, housing_type, street, city, district,
                   rent, deposit, commission, parking, move_in_from, viewings_from, advantages
            FROM offers
            ORDER BY id DESC
        """)
        rows = await cur.fetchall()
        headers = [d[0] for d in cur.description]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
