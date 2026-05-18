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
        self.log(cid, "contract_created", created_by, {"title": title, "requirements": req, "reward_bills": reward_bills, "reward_dollars": reward_dollars, "duration_minutes": duration_minutes})
        return cid

    def list_open_contracts(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT id, title, status, reward_bills, reward_dollars, duration_minutes, created_at, started_at, ends_at FROM contracts WHERE status IN ('open','started') ORDER BY id DESC LIMIT 20").fetchall()

    def list_history_contracts(self, limit: int = 10):
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT id, title, status, reward_bills, reward_dollars, duration_minutes, updated_at
                FROM contracts
                WHERE status IN ('success','failed')
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def get_contract(self, contract_id: int):
        with self.db.connect() as conn:
            contract = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
            if not contract:
                return None
            req = conn.execute("SELECT stat_key, required_level FROM contract_requirements WHERE contract_id=?", (contract_id,)).fetchall()
            parts = conn.execute("SELECT * FROM contract_participants WHERE contract_id=? ORDER BY queue_status ASC, score DESC, created_at ASC", (contract_id,)).fetchall()
            return contract, {r["stat_key"]: int(r["required_level"]) for r in req}, parts

    def candidate_for_member(self, rp_name: str, discord_id: int | str | None, requirements: dict[str, int]) -> Candidate:
        select_cols = ", ".join(["rp_name", "discord_id", *STAT_KEYS])
        row = None
        with self.db.connect() as conn:
            if discord_id:
                row = conn.execute(f"SELECT {select_cols} FROM gta_profiles WHERE discord_id=?", (str(discord_id),)).fetchone()
            if row is None:
                row = conn.execute(f"SELECT {select_cols} FROM gta_profiles WHERE lower(rp_name)=lower(?)", (rp_name,)).fetchone()
        if row is None:
            return Candidate(rp_name, str(discord_id) if discord_id else None, 0, 0, {})
        values = {k: int(row[k] or 0) for k in STAT_KEYS}
        score = sum(min(values.get(k, 0), need) for k, need in requirements.items())
        return Candidate(row["rp_name"], row["discord_id"], score, values.get("contractor", 0), values)

    def add_participant(self, contract_id: int, rp_name: str, discord_id: int | None, actor_id: int) -> None:
        data = self.get_contract(contract_id)
        if not data:
            raise ValueError("Контракт не найден")
        contract, req, _ = data
        if contract["status"] != "open":
            raise ValueError("Запись закрыта: контракт уже начат или завершен")
        self.upsert_profile(rp_name, discord_id, None, {})
        candidate = self.candidate_for_member(rp_name, discord_id, req)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_participants(contract_id, rp_name, discord_id, added_by, queue_status, score)
                VALUES (?, ?, ?, ?, 'waiting', ?)
                ON CONFLICT(contract_id, rp_name) DO UPDATE SET discord_id=EXCLUDED.discord_id, score=EXCLUDED.score
                """,
                (contract_id, candidate.rp_name, str(discord_id) if discord_id else candidate.discord_id, str(actor_id), int(candidate.score)),
            )
        self.rebalance_participants(contract_id)
        self.log(contract_id, "participant_joined", actor_id, {"rp_name": candidate.rp_name, "score": candidate.score})

    def remove_participant(self, contract_id: int, rp_name: str, actor_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM contract_participants WHERE contract_id=? AND rp_name=?", (contract_id, rp_name))
        self.rebalance_participants(contract_id)
        self.log(contract_id, "participant_removed", actor_id, {"rp_name": rp_name})

    def rebalance_participants(self, contract_id: int, max_members: int = 5) -> None:
        data = self.get_contract(contract_id)
        if not data:
            return
        contract, req, parts = data
        if contract["status"] != "open":
            return
        candidates = []
        for p in parts:
            c = self.candidate_for_member(p["rp_name"], p["discord_id"], req)
            candidates.append((p["rp_name"], int(c.score), int(c.contractor)))
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        selected = {rp for rp, _, _ in candidates[:max_members]}
        with self.db.connect() as conn:
            for rp, score, _ in candidates:
                status = "selected" if rp in selected else "waiting"
                conn.execute("UPDATE contract_participants SET queue_status=?, score=? WHERE contract_id=? AND rp_name=?", (status, score, contract_id, rp))

    def promote_waiting(self, contract_id: int, actor_id: int | str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT rp_name FROM contract_participants WHERE contract_id=? AND queue_status='waiting'", (contract_id,)).fetchall()
            conn.execute("UPDATE contract_participants SET queue_status='selected' WHERE contract_id=? AND queue_status='waiting'", (contract_id,))
        count = len(rows)
        self.log(contract_id, "waiting_promoted", actor_id, {"count": count})
        return count

    def start_contract(self, contract_id: int, actor_id: int | str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE contracts SET status='started', started_at=NOW(), ends_at=NOW() + (duration_minutes || ' minutes')::interval, updated_at=NOW() WHERE id=? AND status='open'", (contract_id,))
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
