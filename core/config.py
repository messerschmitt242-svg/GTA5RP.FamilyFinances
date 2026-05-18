import os
from dataclasses import dataclass


def _get_int(name: str, default: int | None = None, required: bool = False) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        if required and default is None:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int
    head_role_id: int

    channel_request: int
    channel_report: int
    channel_approve: int
    channel_family_balance: int
    channel_top_sponsors: int

    passport_channel: int
    car_channel: int
    car_admin_channel: int
    bp_channel: int

    database_url: str

    channel_contract_panel: int
    channel_contract_logs: int
    channel_admin_alerts: int
    channel_available_contracts: int
    channel_contract_history: int

    role_family: int
    role_wrestler: int

    max_contract_members: int = 5


def load_settings() -> Settings:
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Missing required environment variable: TOKEN")

    return Settings(
        token=token,
        guild_id=_get_int("GUILD_ID", 1345261255300218992, required=True),
        head_role_id=_get_int("HEAD_ROLE_ID", 1345267230300049408, required=True),
        channel_request=_get_int("CHANNEL_REQUEST", 1501385708366205028, required=True),
        channel_report=_get_int("CHANNEL_REPORT", 1501351092125040710, required=True),
        channel_approve=_get_int("CHANNEL_APPROVE", 1448688906299113684, required=True),
        channel_family_balance=_get_int("CHANNEL_FAMILY_BALANCE", 1501339448250601472),
        channel_top_sponsors=_get_int("CHANNEL_TOP_SPONSORS", 1447514330252836906),
        passport_channel=_get_int("PASSPORT_CHANNEL", 1447305826644525136, required=True),
        car_channel=_get_int("CAR_CHANNEL", 1447638380933546096, required=True),
        car_admin_channel=_get_int("CAR_ADMIN_CHANNEL", 1503869045974368346, required=True),
        bp_channel=_get_int("BP_CHANNEL", 1497992598504214638, required=True),
        database_url=os.getenv("DATABASE_URL", os.getenv("DATABASE_PATH", "postgresql://postgres:postgres@localhost:5432/postgres")),
        channel_contract_panel=_get_int("CHANNEL_CONTRACT_PANEL", 1505366731881975919, required=True),
        channel_contract_logs=_get_int("CHANNEL_CONTRACT_LOGS", 1505366841185406986, required=True),
        channel_admin_alerts=_get_int("CHANNEL_ADMIN_ALERTS", 1505366944235389040, required=True),
        channel_available_contracts=_get_int("CHANNEL_AVAILABLE_CONTRACTS", _get_int("CHANNEL_CONTRACT_PANEL", 1505366731881975919), required=True),
        channel_contract_history=_get_int("CHANNEL_CONTRACT_HISTORY", _get_int("CHANNEL_CONTRACT_LOGS", 1505366841185406986), required=True),
        role_family=_get_int("ROLE_FAMILY", 1447314644141347008, required=True),
        role_wrestler=_get_int("ROLE_WRESTLER", 1447315536550559846, required=True),
        max_contract_members=_get_int("MAX_CONTRACT_MEMBERS", 5),
    )
