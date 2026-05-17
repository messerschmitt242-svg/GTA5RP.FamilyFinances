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

    def log(self, contract_id: int | None, action: str, actor_id: int, payload: dict[str, Any] | None = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO contract_history(contract_id, action, actor_id, payload) VALUES (?, ?, ?, ?::jsonb)",
                (contract_id, action, str(actor_id), json.dumps(payload or {}, ensure_ascii=False)),
            )

    def upsert_profile(self, rp_name: str, discord_id: int | None, discord_name: str | None, values: dict[str, int]) -> None:
        safe = {k: max(0, int(v)) for k, v in values.items() if k in STAT_KEYS}
        cols = ["rp_name", "discord_id", "discord_name", *safe.keys()]
        vals = [rp_name, str(discord_id) if discord_id else None, discord_name, *safe.values()]
        set_parts = ["discord_id=EXCLUDED.discord_id", "discord_name=EXCLUDED.discord_name", "updated_at=NOW()"]
        set_parts += [f"{k}=EXCLUDED.{k}" for k in safe.keys()]
        q = f"""
            INSERT INTO gta_profiles({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})
            ON CONFLICT(rp_name) DO UPDATE SET {', '.join(set_parts)}
        """
        with self.db.connect() as conn:
            conn.execute(q, tuple(vals))

    def link_guild_members(self, guild) -> int:
        count = 0
        from core.utils import extract_rp_name
        with self.db.connect() as conn:
            rows = conn.execute("SELECT rp_name FROM gta_profiles").fetchall()
            known = {r["rp_name"].lower(): r["rp_name"] for r in rows}
            for member in guild.members:
                if member.bot:
                    continue
                rp = extract_rp_name(member.display_name)
                original = known.get(rp.lower())
                if original:
                    conn.execute("UPDATE gta_profiles SET discord_id=?, discord_name=?, updated_at=NOW() WHERE rp_name=?", (str(member.id), member.display_name, original))
                    count += 1
        return count

    def create_contract(self, title: str, created_by: int, requirements: dict[str, int], source: str = "manual") -> int:
        req = {k: max(0, int(v)) for k, v in requirements.items() if k in STAT_KEYS and int(v) > 0}
        with self.db.connect() as conn:
            row = conn.execute(
                "INSERT INTO contracts(title, created_by, source, status) VALUES (?, ?, ?, 'open') RETURNING id",
                (title, str(created_by), source),
            ).fetchone()
            cid = int(row[0])
            for key, value in req.items():
                conn.execute("INSERT INTO contract_requirements(contract_id, stat_key, required_level) VALUES (?, ?, ?)", (cid, key, value))
        self.log(cid, "contract_created", created_by, {"title": title, "requirements": req})
        return cid

    def list_open_contracts(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, title, status, created_at FROM contracts WHERE status IN ('open','draft') ORDER BY id DESC LIMIT 20").fetchall()

    def get_contract(self, contract_id: int):
        with self.db.connect() as conn:
            contract = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
            if not contract:
                return None
            req = conn.execute("SELECT stat_key, required_level FROM contract_requirements WHERE contract_id=?", (contract_id,)).fetchall()
            parts = conn.execute("SELECT * FROM contract_participants WHERE contract_id=?", (contract_id,)).fetchall()
            return contract, {r["stat_key"]: int(r["required_level"]) for r in req}, parts

    def add_participant(self, contract_id: int, rp_name: str, discord_id: int | None, actor_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO contract_participants(contract_id, rp_name, discord_id, added_by) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (contract_id, rp_name, str(discord_id) if discord_id else None, str(actor_id)),
            )
        self.log(contract_id, "participant_added", actor_id, {"rp_name": rp_name})

    def remove_participant(self, contract_id: int, rp_name: str, actor_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM contract_participants WHERE contract_id=? AND rp_name=?", (contract_id, rp_name))
        self.log(contract_id, "participant_removed", actor_id, {"rp_name": rp_name})

    def close_contract(self, contract_id: int, actor_id: int, status: str = "completed") -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE contracts SET status=?, updated_at=NOW() WHERE id=?", (status, contract_id))
        self.log(contract_id, f"contract_{status}", actor_id)

    def candidates(self, requirements: dict[str, int]) -> list[Candidate]:
        keys = list(requirements.keys())
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
        chance = self.calculate_chance(requirements, picked)
        return picked, remaining, chance

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
