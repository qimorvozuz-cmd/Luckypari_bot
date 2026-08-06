import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    async def init(self):
        async with self._lock:
            with self._connect() as db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT NOT NULL,
                    player_id TEXT, status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contest_entries (
                    contest_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL, PRIMARY KEY(contest_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS freebets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    code TEXT NOT NULL, description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """)

    async def upsert_user(self, user_id: int, username: str | None, full_name: str):
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                db.execute("""INSERT INTO users(user_id, username, full_name, created_at, updated_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username, full_name=excluded.full_name, updated_at=excluded.updated_at""",
                    (user_id, username, full_name, now, now))

    async def submit_player_id(self, user_id: int, player_id: str):
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                db.execute("UPDATE users SET player_id=?, status='pending', updated_at=? WHERE user_id=?",
                           (player_id, now, user_id))

    async def set_status(self, user_id: int, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                cur = db.execute("UPDATE users SET status=?, updated_at=? WHERE user_id=?",
                                 (status, now, user_id))
                return cur.rowcount > 0

    async def get_user(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

    async def pending(self, limit: int = 30):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM users WHERE status='pending' ORDER BY updated_at LIMIT ?",
                                  (limit,)).fetchall()

    async def stats(self):
        async with self._lock:
            with self._connect() as db:
                total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                grouped = dict(db.execute("SELECT status, COUNT(*) FROM users GROUP BY status").fetchall())
                return total, grouped

    async def approved_ids(self):
        async with self._lock:
            with self._connect() as db:
                return [row[0] for row in db.execute("SELECT user_id FROM users WHERE status='approved'")]

    async def all_ids(self):
        async with self._lock:
            with self._connect() as db:
                return [row[0] for row in db.execute("SELECT user_id FROM users")]

    async def create_contest(self, title: str, description: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                db.execute("UPDATE contests SET active=0")
                cur = db.execute("INSERT INTO contests(title,description,created_at) VALUES(?,?,?)",
                                 (title, description, now))
                return cur.lastrowid

    async def active_contest(self):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM contests WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()

    async def join_contest(self, contest_id: int, user_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                cur = db.execute("INSERT OR IGNORE INTO contest_entries VALUES(?,?,?)",
                                 (contest_id, user_id, now))
                return cur.rowcount > 0

    async def contest_count(self, contest_id: int) -> int:
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT COUNT(*) FROM contest_entries WHERE contest_id=?",
                                  (contest_id,)).fetchone()[0]

    async def close_contest(self) -> bool:
        async with self._lock:
            with self._connect() as db:
                return db.execute("UPDATE contests SET active=0 WHERE active=1").rowcount > 0

    async def add_freebet(self, user_id: int, code: str, description: str):
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._connect() as db:
                db.execute("INSERT INTO freebets(user_id,code,description,created_at) VALUES(?,?,?,?)",
                           (user_id, code, description, now))

    async def user_freebets(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM freebets WHERE user_id=? ORDER BY id DESC LIMIT 10",
                                  (user_id,)).fetchall()
