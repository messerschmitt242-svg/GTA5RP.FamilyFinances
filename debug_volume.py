import os

for root, dirs, files in os.walk("/"):
    for file in files:
        if file.endswith(".db") or file.endswith(".sqlite") or file.endswith(".sqlite3"):
            print(os.path.join(root, file))
