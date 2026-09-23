import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


def connect():
    Path(settings.database).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.database, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS shelves (
          id INTEGER PRIMARY KEY, product TEXT NOT NULL, quantity INTEGER NOT NULL,
          capacity INTEGER NOT NULL DEFAULT 12, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shelf_id INTEGER NOT NULL, product TEXT NOT NULL,
          event_type TEXT NOT NULL, previous_quantity INTEGER, new_quantity INTEGER,
          created_at TEXT NOT NULL, screenshot TEXT, detail TEXT
        );
        """)
        for i in range(1, 5):
            db.execute("INSERT OR IGNORE INTO shelves VALUES(?,?,?,?,?)", (i, settings.products[i-1], 0, 12, now()))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def shelves():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM shelves ORDER BY id")]


def events(limit=40):
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]


def update_shelf(shelf_id, quantity, frame=None, event_type=None, detail=None, product=None):
    with connect() as db:
        row = db.execute("SELECT * FROM shelves WHERE id=?", (shelf_id,)).fetchone()
        if not row:
            return None
        previous = row["quantity"]
        product = product or row["product"]
        db.execute("UPDATE shelves SET quantity=?, product=?, updated_at=? WHERE id=?", (quantity, product, now(), shelf_id))
        screenshot = None
        if event_type:
            if frame is not None:
                import cv2
                Path(settings.evidence_dir).mkdir(parents=True, exist_ok=True)
                filename = f"event-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.jpg"
                cv2.imwrite(os.path.join(settings.evidence_dir, filename), frame)
                screenshot = filename
            db.execute("INSERT INTO events(shelf_id,product,event_type,previous_quantity,new_quantity,created_at,screenshot,detail) VALUES(?,?,?,?,?,?,?,?)",
                       (shelf_id, product, event_type, previous, quantity, now(), screenshot, detail))
        return {"previous": previous, "quantity": quantity}
