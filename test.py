import sqlite3

conn = sqlite3.connect("visitas.db")
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tablas:", cursor.fetchall())

cursor.execute("SELECT * FROM usuarios;")
rows = cursor.fetchall()

print("Usuarios:")
for r in rows:
    print(r)