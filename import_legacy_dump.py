import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

DEBTS = [
    {"user_id": "492060270995439618", "amount": 100000},
    {"user_id": "836538564296179732", "amount": 2000000},
    {"user_id": "301338899777847297", "amount": 10000},
]

FAMILY_BANK = [
    {"id": 1, "balance": 13906000},
]

SPONSORS = [
    {"user_id": "245890713517162496", "amount": 2100000},
    {"user_id": "301338899777847297", "amount": 5580000},
    {"user_id": "904321103965585448", "amount": 3250000},
    {"user_id": "1431990880411193406", "amount": 250000},
    {"user_id": "494465117845716992", "amount": 250000},
    {"user_id": "686232927289606160", "amount": 100000},
    {"user_id": "492060270995439618", "amount": 660000},
    {"user_id": "346584209374052355", "amount": 60000},
    {"user_id": "772506083842588703", "amount": 40000},
    {"user_id": "871271861445623829", "amount": 10000},
    {"user_id": "459811965007691796", "amount": 200000},
]

BANK_LOGS = [
    {"id": 1, "action": "DEPOSIT", "amount": 100000, "user_id": "904321103965585448", "time": "07.05 21:32"},
    {"id": 2, "action": "DEPOSIT", "amount": 100000, "user_id": "492060270995439618", "time": "08.05 10:20"},
    {"id": 3, "action": "LOAN", "amount": 1300000, "user_id": "904321103965585448", "time": "08.05 19:18"},
    {"id": 4, "action": "DEPOSIT", "amount": 700000, "user_id": "301338899777847297", "time": "09.05 09:39"},
    {"id": 5, "action": "REPAY", "amount": 100000, "user_id": "1013941461798096997", "time": "09.05 11:24"},
    {"id": 6, "action": "REPAY", "amount": 100000, "user_id": "1013941461798096997", "time": "09.05 16:29"},
    {"id": 7, "action": "DEPOSIT", "amount": 200000, "user_id": "459811965007691796", "time": "09.05 23:34"},
    {"id": 8, "action": "DEPOSIT", "amount": 200000, "user_id": "904321103965585448", "time": "09.05 23:35"},
    {"id": 9, "action": "REPAY", "amount": 550000, "user_id": "904321103965585448", "time": "09.05 23:38"},
    {"id": 10, "action": "DEPOSIT", "amount": 700000, "user_id": "301338899777847297", "time": "10.05 05:27"},
    {"id": 11, "action": "DEPOSIT", "amount": 2000000, "user_id": "301338899777847297", "time": "10.05 13:48"},
    {"id": 12, "action": "LOAN", "amount": 250000, "user_id": "772506083842588703", "time": "10.05 15:11"},
    {"id": 13, "action": "DEPOSIT", "amount": 450000, "user_id": "492060270995439618", "time": "10.05 15:24"},
    {"id": 14, "action": "REPAY", "amount": 250000, "user_id": "772506083842588703", "time": "10.05 15:47"},
    {"id": 15, "action": "LOAN", "amount": 3000000, "user_id": "836538564296179732", "time": "10.05 18:17"},
    {"id": 16, "action": "LOAN", "amount": 2000000, "user_id": "1013941461798096997", "time": "10.05 18:56"},
    {"id": 17, "action": "REPAY", "amount": 2000000, "user_id": "1013941461798096997", "time": "10.05 20:19"},
    {"id": 18, "action": "REPAY", "amount": 0, "user_id": "1013941461798096997", "time": "11.05 11:32"},
    {"id": 19, "action": "DEPOSIT", "amount": 20000, "user_id": "772506083842588703", "time": "11.05 16:47"},
    {"id": 20, "action": "REPAY", "amount": 750000, "user_id": "904321103965585448", "time": "11.05 20:54"},
]

PASSPORTS = [
    {"user_id": "904321103965585448", "passport": "599885", "phone": "6652223"},
    {"user_id": "245890713517162496", "passport": "708996", "phone": "3463250"},
    {"user_id": "492060270995439618", "passport": "660042", "phone": "4778506"},
    {"user_id": "871271861445623829", "passport": "658744", "phone": "7012759"},
    {"user_id": "301338899777847297", "passport": "420780", "phone": "2228222"},
    {"user_id": "836538564296179732", "passport": "370531", "phone": "9971266"},
    {"user_id": "494465117845716992", "passport": "675311", "phone": None},
    {"user_id": "686232927289606160", "passport": "702920", "phone": None},
    {"user_id": "1431990880411193406", "passport": "657775", "phone": None},
    {"user_id": "772506083842588703", "passport": "607795", "phone": "2166061"},
    {"user_id": "459811965007691796", "passport": "435764", "phone": None},
    {"user_id": "1013941461798096997", "passport": "385747", "phone": None},
    {"user_id": "755810521911132263", "passport": "665133", "phone": None},
    {"user_id": "200936298624712704", "passport": "714391", "phone": None},
]

CARS = [
    {"id": 2, "name": "Karin Thunder 2021", "image": "https://cdn.discordapp.com/ephemeral-attachments/1503856805824958526/1503858136413372416/tundra.png?ex=6a04e088&is=6a038f08&hm=3e3b30091a2be045278d232b7a4114524389c0ddca2debab5926a9bb583cb727&", "taken_by": None},
    {"id": 3, "name": "Canis Bodhi", "image": "https://cdn.discordapp.com/ephemeral-attachments/1503856805824958526/1503872383801360474/bodhi2.png?ex=6a04edcc&is=6a039c4c&hm=b5e0ed6f3ac995d07901aa1ad714c459b6c61df63566076ce4fbdacf9ef6cbb5&", "taken_by": None},
]

CAR_LOGS = [
    {"id": 1, "action": "ВЗЯТ", "car_name": "Canis Bodhi", "user_id": "492060270995439618", "time": "12.05 20:35"},
    {"id": 2, "action": "ВОЗВРАЩЕН", "car_name": "Canis Bodhi", "user_id": "492060270995439618", "time": "12.05 20:37"},
    {"id": 3, "action": "ВЗЯТ", "car_name": "Canis Bodhi", "user_id": "904321103965585448", "time": "12.05 20:49"},
    {"id": 4, "action": "ВОЗВРАЩЕН", "car_name": "Canis Bodhi", "user_id": "904321103965585448", "time": "12.05 20:49"},
    {"id": 5, "action": "ВЗЯТ", "car_name": "Karin Thunder 2021", "user_id": "245890713517162496", "time": "12.05 21:13"},
    {"id": 6, "action": "ВОЗВРАЩЕН", "car_name": "Karin Thunder 2021", "user_id": "245890713517162496", "time": "12.05 21:13"},
    {"id": 7, "action": "ВЗЯТ", "car_name": "Karin Thunder 2021", "user_id": "245890713517162496", "time": "12.05 21:14"},
    {"id": 8, "action": "ВЗЯТ", "car_name": "Canis Bodhi", "user_id": "245890713517162496", "time": "12.05 21:14"},
    {"id": 9, "action": "ВОЗВРАЩЕН", "car_name": "Canis Bodhi", "user_id": "245890713517162496", "time": "12.05 21:14"},
    {"id": 10, "action": "ВОЗВРАЩЕН", "car_name": "Karin Thunder 2021", "user_id": "245890713517162496", "time": "12.05 21:14"},
    {"id": 11, "action": "ВЗЯТ", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "16.05 11:56"},
    {"id": 12, "action": "ВОЗВРАЩЕН", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "16.05 14:02"},
    {"id": 13, "action": "ВЗЯТ", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "16.05 14:54"},
    {"id": 14, "action": "ВОЗВРАЩЕН", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "16.05 23:44"},
    {"id": 15, "action": "ВЗЯТ", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "17.05 09:06"},
    {"id": 16, "action": "ВОЗВРАЩЕН", "car_name": "Karin Thunder 2021", "user_id": "772506083842588703", "time": "17.05 17:23"},
]


def create_legacy_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            user_id TEXT PRIMARY KEY,
            amount BIGINT NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS family_bank (
            id INTEGER PRIMARY KEY,
            balance BIGINT NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sponsors (
            user_id TEXT PRIMARY KEY,
            amount BIGINT NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_logs (
            id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            amount BIGINT NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL,
            time TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS passports (
            user_id TEXT PRIMARY KEY,
            passport TEXT,
            phone TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            image TEXT,
            taken_by TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS car_logs (
            id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            car_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            time TEXT
        )
    """)


def upsert_data(cur):
    for r in DEBTS:
        cur.execute("""
            INSERT INTO debts (user_id, amount)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET amount = EXCLUDED.amount
        """, (r["user_id"], r["amount"]))

    for r in FAMILY_BANK:
        cur.execute("""
            INSERT INTO family_bank (id, balance)
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance
        """, (r["id"], r["balance"]))

    for r in SPONSORS:
        cur.execute("""
            INSERT INTO sponsors (user_id, amount)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET amount = EXCLUDED.amount
        """, (r["user_id"], r["amount"]))

    for r in BANK_LOGS:
        cur.execute("""
            INSERT INTO bank_logs (id, action, amount, user_id, time)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                action = EXCLUDED.action,
                amount = EXCLUDED.amount,
                user_id = EXCLUDED.user_id,
                time = EXCLUDED.time
        """, (r["id"], r["action"], r["amount"], r["user_id"], r["time"]))

    for r in PASSPORTS:
        cur.execute("""
            INSERT INTO passports (user_id, passport, phone)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                passport = EXCLUDED.passport,
                phone = EXCLUDED.phone
        """, (r["user_id"], r["passport"], r["phone"]))

    for r in CARS:
        cur.execute("""
            INSERT INTO cars (id, name, image, taken_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                image = EXCLUDED.image,
                taken_by = EXCLUDED.taken_by
        """, (r["id"], r["name"], r["image"], r["taken_by"]))

    for r in CAR_LOGS:
        cur.execute("""
            INSERT INTO car_logs (id, action, car_name, user_id, time)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                action = EXCLUDED.action,
                car_name = EXCLUDED.car_name,
                user_id = EXCLUDED.user_id,
                time = EXCLUDED.time
        """, (r["id"], r["action"], r["car_name"], r["user_id"], r["time"]))


def print_counts(cur):
    for table in ["debts", "family_bank", "sponsors", "bank_logs", "passports", "cars", "car_logs"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"{table}: {count}", flush=True)


def main():
    print("Starting legacy dump import...", flush=True)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            create_legacy_tables(cur)
            upsert_data(cur)
            print_counts(cur)
        conn.commit()
    print("Legacy dump import complete.", flush=True)


if __name__ == "__main__":
    main()
