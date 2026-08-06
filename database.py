import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str, referral_reward: int = 10000):
        self.path = path
        self.referral_reward = referral_reward
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _add_column(db, table: str, name: str, definition: str):
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    async def init(self):
        async with self._lock:
            with self._connect() as db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT NOT NULL,
                    player_id TEXT, status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contest_entries (
                    contest_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL, PRIMARY KEY(contest_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS contest_targets (
                    contest_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    PRIMARY KEY(contest_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS freebets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    code TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                    audience TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS content_targets (
                    content_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    PRIMARY KEY(content_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS referrals (
                    referrer_id INTEGER NOT NULL, referred_id INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending', reward INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, approved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
                CREATE INDEX IF NOT EXISTS idx_content_kind ON content(kind, audience, active);
                """)
                self._add_column(db, "users", "requested_tier", "TEXT NOT NULL DEFAULT 'vip'")
                self._add_column(db, "users", "tier", "TEXT NOT NULL DEFAULT 'none'")
                self._add_column(db, "users", "referred_by", "INTEGER")
                self._add_column(db, "users", "referral_code", "TEXT")
                self._add_column(db, "users", "bonus_balance", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(db, "users", "is_blocked", "INTEGER NOT NULL DEFAULT 0")
                self._add_column(db, "users", "last_seen", "TEXT")
                self._add_column(db, "contests", "audience", "TEXT NOT NULL DEFAULT 'ALL'")
                db.execute("UPDATE users SET referral_code='u' || user_id WHERE referral_code IS NULL")

    async def upsert_user(self, user_id: int, username: str | None, full_name: str,
                          referrer_id: int | None = None) -> bool:
        stamp = now()
        referral_added = False
        async with self._lock:
            with self._connect() as db:
                existing = db.execute("SELECT user_id,referred_by FROM users WHERE user_id=?", (user_id,)).fetchone()
                if existing:
                    db.execute("UPDATE users SET username=?,full_name=?,updated_at=?,last_seen=? WHERE user_id=?",
                               (username, full_name, stamp, stamp, user_id))
                else:
                    valid_ref = None
                    if referrer_id and referrer_id != user_id:
                        valid_ref = db.execute("SELECT user_id FROM users WHERE user_id=?", (referrer_id,)).fetchone()
                    referred_by = referrer_id if valid_ref else None
                    db.execute("""INSERT INTO users
                        (user_id,username,full_name,status,created_at,updated_at,last_seen,referral_code,referred_by)
                        VALUES(?,?,?,'new',?,?,?,?,?)""",
                        (user_id, username, full_name, stamp, stamp, stamp, f"u{user_id}", referred_by))
                    if referred_by:
                        db.execute("INSERT OR IGNORE INTO referrals(referrer_id,referred_id,created_at) VALUES(?,?,?)",
                                   (referred_by, user_id, stamp))
                        referral_added = True
        return referral_added

    async def submit_application(self, user_id: int, player_id: str, tier: str):
        async with self._lock:
            with self._connect() as db:
                db.execute("UPDATE users SET player_id=?,requested_tier=?,status='pending',updated_at=? WHERE user_id=?",
                           (player_id, tier, now(), user_id))

    async def approve_application(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                user = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
                if not user:
                    return None, None
                tier = user["requested_tier"] if user["requested_tier"] in {"vip", "mega"} else "vip"
                db.execute("UPDATE users SET status='approved',tier=?,is_blocked=0,updated_at=? WHERE user_id=?",
                           (tier, now(), user_id))
                referral = db.execute("SELECT * FROM referrals WHERE referred_id=? AND status='pending'", (user_id,)).fetchone()
                rewarded_referrer = None
                if referral:
                    reward = self.referral_reward
                    db.execute("UPDATE referrals SET status='approved',reward=?,approved_at=? WHERE referred_id=?",
                               (reward, now(), user_id))
                    db.execute("UPDATE users SET bonus_balance=bonus_balance+? WHERE user_id=?",
                               (reward, referral["referrer_id"]))
                    rewarded_referrer = referral["referrer_id"]
                return tier, rewarded_referrer

    async def reject_application(self, user_id: int) -> bool:
        return await self.set_status(user_id, "rejected")

    async def set_status(self, user_id: int, status: str) -> bool:
        async with self._lock:
            with self._connect() as db:
                return db.execute("UPDATE users SET status=?,updated_at=? WHERE user_id=?",
                                  (status, now(), user_id)).rowcount > 0

    async def set_tier(self, user_id: int, tier: str) -> bool:
        status = "approved" if tier in {"vip", "mega"} else "revoked"
        async with self._lock:
            with self._connect() as db:
                return db.execute("UPDATE users SET tier=?,status=?,updated_at=? WHERE user_id=?",
                                  (tier, status, now(), user_id)).rowcount > 0

    async def set_blocked(self, user_id: int, blocked: bool) -> bool:
        async with self._lock:
            with self._connect() as db:
                return db.execute("UPDATE users SET is_blocked=?,updated_at=? WHERE user_id=?",
                                  (int(blocked), now(), user_id)).rowcount > 0

    async def get_user(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

    async def pending(self, limit: int = 50):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM users WHERE status='pending' ORDER BY updated_at LIMIT ?", (limit,)).fetchall()

    async def all_ids(self):
        async with self._lock:
            with self._connect() as db:
                return [row[0] for row in db.execute("SELECT user_id FROM users WHERE is_blocked=0")]

    async def audience_ids(self, audience: str):
        async with self._lock:
            with self._connect() as db:
                if audience == "ALL":
                    rows = db.execute("SELECT user_id FROM users WHERE status='approved' AND is_blocked=0")
                elif audience == "VIP":
                    rows = db.execute("SELECT user_id FROM users WHERE status='approved' AND tier='vip' AND is_blocked=0")
                else:
                    rows = db.execute("SELECT user_id FROM users WHERE status='approved' AND tier='mega' AND is_blocked=0")
                return [row[0] for row in rows]

    async def stats(self):
        async with self._lock:
            with self._connect() as db:
                total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                grouped = dict(db.execute("SELECT status,COUNT(*) FROM users GROUP BY status").fetchall())
                tiers = dict(db.execute("SELECT tier,COUNT(*) FROM users WHERE status='approved' GROUP BY tier").fetchall())
                referrals = db.execute("SELECT COUNT(*) FROM referrals WHERE status='approved'").fetchone()[0]
                return total, grouped, tiers, referrals

    async def create_contest(self, title: str, description: str, audience: str) -> int:
        async with self._lock:
            with self._connect() as db:
                cur = db.execute("INSERT INTO contests(title,description,audience,created_at) VALUES(?,?,?,?)",
                                 (title, description, audience, now()))
                return cur.lastrowid

    async def set_contest_targets(self, contest_id: int, user_ids: list[int]):
        async with self._lock:
            with self._connect() as db:
                db.executemany("INSERT OR IGNORE INTO contest_targets VALUES(?,?)",
                               [(contest_id, user_id) for user_id in user_ids])

    async def active_contests(self, user_id: int, tier: str):
        audience = "MEGA" if tier == "mega" else "VIP"
        async with self._lock:
            with self._connect() as db:
                return db.execute("""SELECT DISTINCT c.* FROM contests c
                    LEFT JOIN contest_targets t ON t.contest_id=c.id
                    WHERE c.active=1 AND (c.audience IN ('ALL',?) OR t.user_id=?)
                    ORDER BY c.id DESC LIMIT 10""", (audience, user_id)).fetchall()

    async def join_contest(self, contest_id: int, user_id: int) -> bool:
        async with self._lock:
            with self._connect() as db:
                contest = db.execute("SELECT active FROM contests WHERE id=?", (contest_id,)).fetchone()
                if not contest or not contest["active"]:
                    return False
                return db.execute("INSERT OR IGNORE INTO contest_entries VALUES(?,?,?)",
                                  (contest_id, user_id, now())).rowcount > 0

    async def contest_count(self, contest_id: int) -> int:
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT COUNT(*) FROM contest_entries WHERE contest_id=?", (contest_id,)).fetchone()[0]

    async def close_contests(self) -> int:
        async with self._lock:
            with self._connect() as db:
                return db.execute("UPDATE contests SET active=0 WHERE active=1").rowcount

    async def add_content(self, kind: str, audience: str, title: str, body: str) -> int:
        async with self._lock:
            with self._connect() as db:
                cur = db.execute("INSERT INTO content(kind,audience,title,body,created_at) VALUES(?,?,?,?,?)",
                                 (kind, audience, title, body, now()))
                return cur.lastrowid

    async def set_content_targets(self, content_id: int, user_ids: list[int]):
        async with self._lock:
            with self._connect() as db:
                db.executemany("INSERT OR IGNORE INTO content_targets VALUES(?,?)",
                               [(content_id, user_id) for user_id in user_ids])

    async def latest_content(self, kind: str, user_id: int, tier: str, limit: int = 10):
        audience = "MEGA" if tier == "mega" else "VIP"
        async with self._lock:
            with self._connect() as db:
                return db.execute("""SELECT DISTINCT c.* FROM content c
                    LEFT JOIN content_targets t ON t.content_id=c.id
                    WHERE c.kind=? AND c.active=1 AND (c.audience IN ('ALL',?) OR t.user_id=?)
                    ORDER BY c.id DESC LIMIT ?""", (kind, audience, user_id, limit)).fetchall()

    async def add_freebet(self, user_id: int, code: str, description: str):
        async with self._lock:
            with self._connect() as db:
                db.execute("INSERT INTO freebets(user_id,code,description,created_at) VALUES(?,?,?,?)",
                           (user_id, code, description, now()))

    async def user_freebets(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM freebets WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)).fetchall()

    async def referral_stats(self, user_id: int):
        async with self._lock:
            with self._connect() as db:
                total = db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()[0]
                approved = db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='approved'", (user_id,)).fetchone()[0]
                user = db.execute("SELECT referral_code,bonus_balance FROM users WHERE user_id=?", (user_id,)).fetchone()
                return total, approved, user

    async def bonus_users(self):
        async with self._lock:
            with self._connect() as db:
                return db.execute("SELECT * FROM users WHERE bonus_balance>0 ORDER BY bonus_balance DESC").fetchall()

    async def clear_bonus(self, user_id: int) -> int:
        async with self._lock:
            with self._connect() as db:
                row = db.execute("SELECT bonus_balance FROM users WHERE user_id=?", (user_id,)).fetchone()
                amount = row[0] if row else 0
                db.execute("UPDATE users SET bonus_balance=0 WHERE user_id=?", (user_id,))
                return amount
