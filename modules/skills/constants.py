from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDef:
    key: str
    ru: str
    aliases: tuple[str, ...] = ()


SKILLS: tuple[SkillDef, ...] = (
    SkillDef("strength", "Сила"),
    SkillDef("shooting", "Стрельба"),
    SkillDef("cooking", "Кулинария"),
    SkillDef("fishing", "Рыболовство", ("Рыбалка",)),
    SkillDef("hunting", "Охота"),
    SkillDef("treasure", "Поиск сокровищ", ("Сокровища",)),
    SkillDef("farming", "Фермерство"),
    SkillDef("builder", "Строитель", ("Стройка",)),
    SkillDef("miner", "Шахтёр", ("Шахтер", "Шахта")),
    SkillDef("loader", "Грузчик"),
    SkillDef("taxi", "Таксист"),
    SkillDef("diver", "Дайвер"),
    SkillDef("collector", "Инкассатор"),
    SkillDef("bus_driver", "Водитель автобуса", ("Автобус",)),
    SkillDef("mechanic", "Механик"),
    SkillDef("firefighter", "Пожарный"),
    SkillDef("trucker", "Дальнобойщик"),
    SkillDef("courier", "Курьер"),
    SkillDef("contractor", "Подрядчик"),
    SkillDef("postman", "Почтальон"),
)

RANKS: tuple[SkillDef, ...] = (
    SkillDef("bandit_rank", "Бандит"),
    SkillDef("mafia_rank", "Мафиози"),
    SkillDef("police_rank", "Полицейский"),
    SkillDef("sheriff_rank", "Шериф"),
    SkillDef("federal_rank", "Федеральный агент", ("Фед. агент", "Федерал")),
    SkillDef("army_rank", "Солдат"),
    SkillDef("medic_rank", "Врач"),
    SkillDef("reporter_rank", "Репортёр", ("Репортер",)),
    SkillDef("goverment_rank", "Говермент", ("Government", "Правительство", "Госслужащий")),
)



CLUBS: tuple[SkillDef, ...] = (
    SkillDef("merryweather_club", "Merryweather Club"),
    SkillDef("rednecks_club", "Rednecks Club"),
    SkillDef("moto_club", "Moto Club"),
    SkillDef("auto_club", "Auto Club"),
    SkillDef("epsilon_club", "Epsilon Club"),
)

ALL_STATS = SKILLS + RANKS + CLUBS
STAT_BY_KEY = {s.key: s for s in ALL_STATS}
STAT_KEYS = tuple(STAT_BY_KEY.keys())

CONTRACTOR_BONUS = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}


def stat_name(key: str) -> str:
    return STAT_BY_KEY.get(key, SkillDef(key, key)).ru
