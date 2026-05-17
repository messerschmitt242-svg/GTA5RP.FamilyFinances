import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg


class Row(dict):
    """Small compatibility row: supports row['name'] and row[0]."""

    def __init__(self, columns: list[str], values: tuple[Any, ...]):
        super().__init__(zip(columns, values))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class CursorCompat:
    def __init__(self, cursor):
        self.cursor = cursor
        self._columns: list[str] = []

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        query = query.replace("?", "%s")
        self.cursor.execute(query, params or ())
        self._columns = [d.name for d in self.cursor.description] if self.cursor.description else []
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(self._columns, row) if row is not None else None

    def fetchall(self):
        return [Row(self._columns, row) for row in self.cursor.fetchall()]


class ConnectionCompat:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        cur = CursorCompat(self.conn.cursor())
        return cur.execute(query, params)

    def executescript(self, script: str) -> None:
        self.conn.execute(script)


class Database:
    """PostgreSQL database with a tiny sync compatibility layer for old modules."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[ConnectionCompat]:
        with psycopg.connect(self.database_url) as conn:
            yield ConnectionCompat(conn)
            conn.commit()

    def init_schema(self) -> None:
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debts (
                    user_id TEXT PRIMARY KEY,
                    amount INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0)
                );

                CREATE TABLE IF NOT EXISTS family_bank (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0)
                );

                INSERT INTO family_bank (id, balance) VALUES (1, 0)
                ON CONFLICT (id) DO NOTHING;

                CREATE TABLE IF NOT EXISTS sponsors (
                    user_id TEXT PRIMARY KEY,
                    amount INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0)
                );

                CREATE TABLE IF NOT EXISTS bank_logs (
                    id BIGSERIAL PRIMARY KEY,
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
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    image TEXT NOT NULL,
                    taken_by TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS car_logs (
                    id BIGSERIAL PRIMARY KEY,
                    action TEXT NOT NULL,
                    car_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    time TEXT NOT NULL
                );
            """)
            self.init_contracts_schema(conn)

    def init_contracts_schema(self, conn) -> None:
        skill_columns = ",\n".join([f"{name} INTEGER NOT NULL DEFAULT 0 CHECK({name} >= 0)" for name in CONTRACT_STAT_COLUMNS])
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS gta_profiles (
                rp_name TEXT PRIMARY KEY,
                discord_id TEXT UNIQUE,
                discord_name TEXT,
                {skill_columns},
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        for column in CONTRACT_STAT_COLUMNS:
            conn.execute(f"ALTER TABLE gta_profiles ADD COLUMN IF NOT EXISTS {column} INTEGER NOT NULL DEFAULT 0 CHECK({column} >= 0)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_by TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                source TEXT NOT NULL DEFAULT 'manual',
                preview_message_id TEXT,
                panel_message_id TEXT
            );

            CREATE TABLE IF NOT EXISTS contract_requirements (
                contract_id BIGINT NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
                stat_key TEXT NOT NULL,
                required_level INTEGER NOT NULL CHECK(required_level >= 0),
                PRIMARY KEY(contract_id, stat_key)
            );

            CREATE TABLE IF NOT EXISTS contract_participants (
                contract_id BIGINT NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
                rp_name TEXT NOT NULL REFERENCES gta_profiles(rp_name) ON DELETE CASCADE,
                discord_id TEXT,
                added_by TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(contract_id, rp_name)
            );

            CREATE TABLE IF NOT EXISTS contract_history (
                id BIGSERIAL PRIMARY KEY,
                contract_id BIGINT,
                action TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)


CONTRACT_STAT_COLUMNS = [
    "strength", "shooting", "cooking", "fishing", "hunting", "treasure", "farming",
    "builder", "miner", "loader", "taxi", "diver", "collector", "bus_driver",
    "mechanic", "firefighter", "trucker", "courier", "contractor", "postman",
    "bandit_rank", "mafia_rank", "police_rank", "sheriff_rank", "federal_rank",
    "army_rank", "medic_rank", "reporter_rank", "goverment_rank",
]
