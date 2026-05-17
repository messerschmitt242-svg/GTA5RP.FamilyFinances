from core.bot import WayneBot
from core.config import load_settings
from core.database import Database

import shutil

shutil.copy("/data/family_finance.db", "family_finance.db")

def main() -> None:
    settings = load_settings()
    db = Database(settings.database_url)
    bot = WayneBot(settings, db)
    bot.run(settings.token)


if __name__ == "__main__":
    main()
