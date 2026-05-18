from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from modules.skills.constants import CONTRACTOR_BONUS, STAT_KEYS, stat_name


@dataclass
class Candidate:
    rp_name: str
    discord_id: str | None
    score: int
    contractor: int
    values: dict[str, int]


class ContractService:
    def __init__(self, db):
        self.db = db

    def log(self, contract_id: int | None, action: str, actor_id: int | str, payload: dict[str, Any] | None = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO contract_history(contract_id, action, actor_id, payload) VALUES (?, ?, ?, ?::jsonb)",
                (contract_id, action, str(actor_id), json.dumps(payload or {}, ensure_ascii=False)),
            )

    def wipe_contracts(self, actor_id: int | str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM contract_waitlist")
            conn.execute("DELETE FROM contract_participants")
            conn.execute("DELETE FROM contract_requirements")
            conn.execute("DELETE FROM contract_history")
            conn.execute("DELETE FROM contracts")
            conn.execute("ALTER SEQUENCE IF EXISTS contracts_id_seq RESTART WITH 1")
            conn.execute("ALTER SEQUENCE IF EXISTS contract_history_id_seq RESTART WITH 1")

    def upsert_profile(self, rp_name: str, discord_id: int | str | None, discord_name: str | None, values: dict[str, int]) -> None:
        rp_name = rp_name.strip()
        if not rp_name:
            raise ValueError("RP nickname не может быть пустым")
        safe = {k: max(0, int(v)) for k, v in values.items() if k in STAT_KEYS}
        cols = ["rp_name", "discord_id", "discord_name", *safe.keys()]
        vals = [rp_name, str(discord_id) if discord_id else None, discord_name, *safe.values()]
        set_parts = ["updated_at=NOW()"]
        if discord_id:
            set_parts.append("discord_id=EXCLUDED.discord_id")
        if discord_name:
            set_parts.append("discord_name=EXCLUDED.discord_name")
        set_parts += [f"{k}=EXCLUDED.{k}" for k in safe.keys()]
        q = f"""
            INSERT INTO gta_profiles({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})
            ON CONFLICT(rp_name) DO UPDATE SET {', '.join(set_parts)}
        """
        with self.db.connect() as conn:
            conn.execute(q, tuple(vals))

    def update_profile_skill(self, rp_name: str, stat_key: str, value: int, actor_id: int | str) -> None:
        if stat_key not in STAT_KEYS:
            raise ValueError("Неизвестный навык")
        with self.db.connect() as conn:
            conn.execute(f"UPDATE gta_profiles SET {stat_key}=?, updated_at=NOW() WHERE rp_name=?", (int(value), rp_name))
        self.log(None, "profile_skill_updated", actor_id, {"rp_name": rp_name, "stat_key": stat_key, "value": int(value)})

    def list_profiles(self, limit: int = 100):
        with self.db.connect() as conn:
            return conn.execute("SELECT rp_name, discord_id, discord_name FROM gta_profiles ORDER BY rp_name ASC LIMIT ?", (limit,)).fetchall()

    def create_contract(self, title: str, created_by: int | str, requirements: dict[str, int], source: str = "manual", reward_bills: int = 0, reward_dollars: int = 0, duration_minutes: int = 0) -> int:
        req = {k: max(0, int(v)) for k, v in requirements.items() if k in STAT_KEYS and int(v) > 0}
        with self.db.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO contracts(title, created_by, source, status, reward_bills, reward_dollars, duration_minutes)
                VALUES (?, ?, ?, 'open', ?, ?, ?) RETURNING id
                """,
                (title.strip(), str(created_by), source, int(reward_bills), int(reward_dollars), int(duration_minutes)),
            ).fetchone()
            cid = int(row[0])
            for key, value in req.items():
                conn.execute("INSERT INTO contract_requirements(contract_id, stat_key, required_level) VALUES (?, ?, ?)", (cid, key, value))
        self.log(cid, "contract_created", created_by, {"title": title, "requirements": req})
        return cid

    def set_available_message_id(self, contract_id: int, message_id: int | str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE contracts SET available_message_id=?, updated_at=NOW() WHERE id=?", (str(message_id), contract_id))

    def list_open_contracts(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, title, status, reward_bills, reward_dollars, duration_minutes, created_at, started_at FROM contracts WHERE status IN ('open','started') ORDER BY id DESC LIMIT 20").fetchall()

    def list_history_contracts(self, limit: int = 10):
        with self.db.connect() as conn:
            return conn.execute("""
                SELECT id, title, status, reward_bills, reward_dollars, duration_minutes, updated_at
                FROM contracts WHERE status IN ('success','failed')
                ORDER BY updated_at DESC, id DESC LIMIT ?
            """, (limit,)).fetchall()

    def get_contract(self, contract_id: int):
        with self.db.connect() as conn:
            contract = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
            if not contract:
                return None
            req = conn.execute("SELECT stat_key, required_level FROM contract_requirements WHERE contract_id=?", (contract_id,)).fetchall()
            parts = conn.execute("SELECT * FROM contract_participants WHERE contract_id=? ORDER BY created_at ASC", (contract_id,)).fetchall()
            wait = conn.execute("SELECT * FROM contract_waitlist WHERE contract_id=? ORDER BY created_at ASC", (contract_id,)).fetchall()
            return contract, {r["stat_key"]: int(r["required_level"]) for r in req}, parts, wait

    def _profile_values(self, conn, rp_name: str) -> dict[str, int]:
        cols = ", ".join(STAT_KEYS)
        row = conn.execute(f"SELECT {cols} FROM gta_profiles WHERE rp_name=?", (rp_name,)).fetchone()
        if not row:
            return {k: 0 for k in STAT_KEYS}
        return {k: int(row[k] or 0) for k in STAT_KEYS}

    def _score_profile(self, values: dict[str, int], requirements: dict[str, int]) -> int:
        return sum(min(values.get(k, 0), need) for k, need in requirements.items())

    def rebalance_contract_members(self, contract_id: int, max_members: int = 5) -> None:
        data = self.get_contract(contract_id)
        if not data:
            return
        _, req, parts, wait = data
        joined = {r["rp_name"]: r for r in [*parts, *wait]}
        with self.db.connect() as conn:
            scored = []
            for rp_name, row in joined.items():
                values = self._profile_values(conn, rp_name)
                scored.append((self._score_profile(values, req), rp_name, row))
            scored.sort(key=lambda x: (x[0], x[1].lower()), reverse=True)
            top = scored[:max_members]
            rest = scored[max_members:]
            conn.execute("DELETE FROM contract_participants WHERE contract_id=?", (contract_id,))
            conn.execute("DELETE FROM contract_waitlist WHERE contract_id=?", (contract_id,))
            for _, rp_name, row in top:
                conn.execute("INSERT INTO contract_participants(contract_id, rp_name, discord_id, added_by) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", (contract_id, rp_name, row.get("discord_id"), row.get("added_by") or row.get("discord_id") or "system"))
            for _, rp_name, row in rest:
                conn.execute("INSERT INTO contract_waitlist(contract_id, rp_name, discord_id, added_by) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", (contract_id, rp_name, row.get("discord_id"), row.get("added_by") or row.get("discord_id") or "system"))

    def add_participant(self, contract_id: int, rp_name: str, discord_id: int | None, actor_id: int, max_members: int = 5) -> None:
        self.upsert_profile(rp_name, discord_id, None, {})
        with self.db.connect() as conn:
            conn.execute("DELETE FROM contract_waitlist WHERE contract_id=? AND rp_name=?", (contract_id, rp_name))
            conn.execute("INSERT INTO contract_participants(contract_id, rp_name, discord_id, added_by) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", (contract_id, rp_name, str(discord_id) if discord_id else None, str(actor_id)))
        self.rebalance_contract_members(contract_id, max_members)
        self.log(contract_id, "participant_joined", actor_id, {"rp_name": rp_name})

    def promote_waitlist(self, contract_id: int, actor_id: int | str, max_members: int = 5) -> int:
        data = self.get_contract(contract_id)
        if not data:
            return 0
        _, _, parts, wait = data
        slots = max(0, max_members - len(parts))
        moved = 0
        with self.db.connect() as conn:
            for row in wait[:slots]:
                conn.execute("DELETE FROM contract_waitlist WHERE contract_id=? AND rp_name=?", (contract_id, row["rp_name"]))
                conn.execute("INSERT INTO contract_participants(contract_id, rp_name, discord_id, added_by) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", (contract_id, row["rp_name"], row.get("discord_id"), str(actor_id)))
                moved += 1
        self.log(contract_id, "waitlist_promoted", actor_id, {"moved": moved})
        return moved

    def remove_participant(self, contract_id: int, rp_name: str, actor_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM contract_participants WHERE contract_id=? AND rp_name=?", (contract_id, rp_name))
            conn.execute("DELETE FROM contract_waitlist WHERE contract_id=? AND rp_name=?", (contract_id, rp_name))
        self.rebalance_contract_members(contract_id)
        self.log(contract_id, "participant_removed", actor_id, {"rp_name": rp_name})

    def start_contract(self, contract_id: int, actor_id: int | str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE contracts SET status='started', started_at=NOW(), updated_at=NOW() WHERE id=? AND status='open'", (contract_id,))
        self.log(contract_id, "contract_started", actor_id)

    def close_contract(self, contract_id: int, actor_id: int, status: str) -> None:
        if status not in {"success", "failed"}:
            raise ValueError("Статус должен быть success или failed")
        with self.db.connect() as conn:
            conn.execute("UPDATE contracts SET status=?, updated_at=NOW() WHERE id=?", (status, contract_id))
        self.log(contract_id, f"contract_{status}", actor_id)

    def candidates(self, requirements: dict[str, int]) -> list[Candidate]:
        select_cols = ", ".join(["rp_name", "discord_id", *STAT_KEYS])
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT {select_cols} FROM gta_profiles").fetchall()
        out: list[Candidate] = []
        for r in rows:
            values = {k: int(r[k] or 0) for k in STAT_KEYS}
            score = sum(min(values.get(k, 0), need) for k, need in requirements.items())
            if score <= 0:
                continue
            out.append(Candidate(r["rp_name"], r["discord_id"], score, values.get("contractor", 0), values))
        out.sort(key=lambda c: (c.score, c.contractor), reverse=True)
        return out

    def suggest_team(self, requirements: dict[str, int], max_members: int = 5) -> tuple[list[Candidate], dict[str, int], int]:
        remaining = dict(requirements)
        picked: list[Candidate] = []
        candidates = self.candidates(requirements)
        for _ in range(max_members):
            best = None
            best_gain = 0
            for c in candidates:
                if c in picked:
                    continue
                gain = sum(min(c.values.get(k, 0), need) for k, need in remaining.items())
                if gain > best_gain:
                    best = c
                    best_gain = gain
            if not best or best_gain <= 0:
                break
            picked.append(best)
            for k in remaining:
                remaining[k] = max(0, remaining[k] - best.values.get(k, 0))
            if all(v <= 0 for v in remaining.values()):
                break
        return picked, remaining, self.calculate_chance(requirements, picked)

    def calculate_chance(self, requirements: dict[str, int], team: list[Candidate]) -> int:
        if not requirements:
            return 0
        coverage = []
        for k, need in requirements.items():
            have = sum(c.values.get(k, 0) for c in team)
            coverage.append(min(1.0, have / need) if need > 0 else 1.0)
        base = int((sum(coverage) / len(coverage)) * 100)
        bonus = sum(CONTRACTOR_BONUS.get(min(max(c.contractor, 0), 5), 10 if c.contractor > 5 else 0) for c in team)
        return min(100, base + bonus)


def format_requirements(req: dict[str, int]) -> str:
    return "\n".join(f"• **{stat_name(k)}:** {v}" for k, v in req.items()) or "—"


def format_duration(minutes: int | None) -> str:
    minutes = int(minutes or 0)
    if minutes <= 0:
        return "—"
    return f"{minutes // 60} ч. {minutes % 60:02d} мин."
