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



def has_role(member: discord.Member, role_id: int) -> bool:
    return any(role.id == role_id for role in getattr(member, "roles", []))


def has_any_role(member: discord.Member, *role_ids: int) -> bool:
    owned = {role.id for role in getattr(member, "roles", [])}
    return any(role_id in owned for role_id in role_ids)


def extract_rp_name(display_name: str) -> str:
    """Extract GTA RP name from Discord display name.

    Examples:
    Wolf_Wayne [Саня] -> Wolf_Wayne
    John Wick [Джон] -> John Wick
    """
    return display_name.split("[")[0].strip()


async def clear_channel(channel: discord.abc.Messageable, limit: int = 100) -> None:
    """Delete recent messages from a terminal/panel channel before posting a fresh embed.

    This prevents duplicated panel embeds after Railway redeploys. If the bot lacks
    permissions, the error is swallowed so startup does not crash.
    """
    try:
        if hasattr(channel, "purge"):
            await channel.purge(limit=limit, check=lambda _m: True)
    except Exception as exc:
        print(f"CLEAR CHANNEL ERROR: {exc}")
