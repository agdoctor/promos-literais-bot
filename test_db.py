import sqlite3
import traceback

DB_PATH = "bot_data.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    from config import SOURCE_CHANNELS
    for ch in SOURCE_CHANNELS:
        c.execute("INSERT OR IGNORE INTO canais (nome_ou_link) VALUES (?)", (ch.strip(),))
    
    # Configs padrão
    c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('pausado', '0')")

    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            image_path TEXT,
            post_url TEXT,
            short_code TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("Sucesso!")
except Exception as e:
    traceback.print_exc()

conn.commit()
conn.close()
