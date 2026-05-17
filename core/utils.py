import discord


def is_head(member: discord.Member, head_role_id: int) -> bool:
    return any(role.id == head_role_id for role in getattr(member, "roles", []))


async def resolve_member(guild: discord.Guild, text: str) -> discord.Member | None:
    text = text.strip()
    if text.startswith("<@") and text.endswith(">"):
        try:
            uid = int(text.replace("<@", "").replace(">", "").replace("!", ""))
            member = guild.get_member(uid)
            if member:
                return member
        except ValueError:
            pass

    text_l = text.lower()
    for member in guild.members:
        if text_l in member.display_name.lower() or text_l in member.name.lower():
            return member
    return None


def parse_positive_int(value: str) -> int | None:
    try:
        amount = int(value.replace(" ", "").replace(",", ""))
    except ValueError:
        return None
    return amount if amount > 0 else None


async def safe_pin(message: discord.Message) -> None:
    try:
        if not message.pinned:
            await message.pin()
    except Exception:
        pass
