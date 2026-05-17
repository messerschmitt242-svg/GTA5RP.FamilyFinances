import os

print("========== VOLUME DEBUG START ==========")

paths = [
    "/app",
    "/data",
    "/railway",
    "/var/lib/containers/railwayapp/bind-mounts",
]

for p in paths:
    print(f"\n--- CHECK: {p} ---")
    if os.path.exists(p):
        print("EXISTS")
        try:
            print(os.listdir(p)[:50])
        except Exception as e:
            print("LIST ERROR:", e)
    else:
        print("NOT EXISTS")

print("\n--- SEARCH DB FILES ---")

found = False

for root, dirs, files in os.walk("/"):
    if root.startswith("/proc") or root.startswith("/sys") or root.startswith("/dev"):
        continue

    for file in files:
        if file.endswith((".db", ".sqlite", ".sqlite3")):
            found = True
            print("FOUND:", os.path.join(root, file))

if not found:
    print("NO DATABASE FILES FOUND")

print("========== VOLUME DEBUG END ==========")
