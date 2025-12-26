import sqlite3

conn = sqlite3.connect("data/bot.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    broker TEXT,
    status TEXT
)
""")

conn.commit()

def add_offer(offer_id, broker):
    cur.execute("INSERT INTO offers VALUES (?, ?, ?)", (offer_id, broker, "Активна"))
    conn.commit()
