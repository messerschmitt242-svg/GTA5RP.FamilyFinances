import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator


class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                yield conn
                conn.commit()
            finally:
                conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS debts (
                    user_id TEXT PRIMARY KEY,
                    amount INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0)
                );

                CREATE TABLE IF NOT EXISTS family_bank (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0)
                );

                INSERT OR IGNORE INTO family_bank (id, balance) VALUES (1, 0);

                CREATE TABLE IF NOT EXISTS sponsors (
                    user_id TEXT PRIMARY KEY,
                    amount INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0)
                );

                CREATE TABLE IF NOT EXISTS bank_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT NOT NULL,
                    time TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS passports (
                    user_id TEXT PRIMARY KEY,
                    passport TEXT UNIQUE NOT NULL,
                    phone TEXT
                );

                CREATE TABLE IF NOT EXISTS cars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    image TEXT NOT NULL,
                    taken_by TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS car_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    car_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    time TEXT NOT NULL
                );
                """
            )
            # Safe migration for older DBs that were created before phone existed.
            columns = [row[1] for row in conn.execute("PRAGMA table_info(passports)").fetchall()]
            if "phone" not in columns:
                conn.execute("ALTER TABLE passports ADD COLUMN phone TEXT")
