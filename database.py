import sqlite3
import time
from typing import Optional

DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabela para canais que o Userbot vai monitorar
    c.execute('''
        CREATE TABLE IF NOT EXISTS canais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_ou_link TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Tabela para palavras-chave que o Userbot deve procurar
    c.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palavra TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Tabela para palavras-chave negativas
    c.execute('''
        CREATE TABLE IF NOT EXISTS negative_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palavra TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Tabela para configurações gerais do bot (Chave -> Valor)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')
    
    # Inserir dados padrão baseados no seu .env só pra começar
    try:
        from config import SOURCE_CHANNELS
        for ch in SOURCE_CHANNELS:
            c.execute("INSERT OR IGNORE INTO canais (nome_ou_link) VALUES (?)", (ch.strip(),))
        
        # Configs padrão
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('pausado', '0')")
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('aprovacao_manual', '0')")
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('preco_minimo', '0')")
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('delay_minutos', '0')")
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('assinatura', '')")
        c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('cooldown_minutos', '60')")

        # --- NOVAS TABELAS ---

        # Tabela de Histórico para Deduplicação (Cooldown 60 min)
        c.execute('''
            CREATE TABLE IF NOT EXISTS history (
                hash_id TEXT PRIMARY KEY,
                posted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de Administradores
        c.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        ''')

        # Tabela de Sorteios
        c.execute('''
            CREATE TABLE IF NOT EXISTS sorteios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                premio TEXT NOT NULL,
                status TEXT DEFAULT 'aberto', -- 'aberto', 'encerrado'
                ganhador_id INTEGER,
                ganhador_nome TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    except:
        pass
        
    conn.commit()
    conn.close()

def get_canais():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT nome_ou_link FROM canais")
    canais = [row[0] for row in c.fetchall()]
    conn.close()
    return canais

def normalize_channel(nome: str) -> str:
    """Extrai apenas o username de links ou remove o @."""
    nome = nome.strip()
    # Se for link do tipo https://t.me/username ou t.me/username
    if "t.me/" in nome:
        nome = nome.split("t.me/")[-1]
    # Remove @ inicial se existir
    if nome.startswith("@"):
        nome = nome[1:]
    # Remove barras finais se houver
    nome = nome.split("/")[0]
    return nome

def add_canal(nome: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        nome_limpo = normalize_channel(nome)
        if not nome_limpo:
            return False
        c.execute("INSERT INTO canais (nome_ou_link) VALUES (?)", (nome_limpo,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_canal(nome: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM canais WHERE nome_ou_link = ?", (nome.strip(),))
    conn.commit()
    conn.close()

def get_keywords():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT palavra FROM keywords ORDER BY palavra ASC")
    kws = [row[0] for row in c.fetchall()]
    conn.close()
    return kws

def add_keyword(kw: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO keywords (palavra) VALUES (?)", (kw.strip().lower(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_keyword(kw: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM keywords WHERE palavra = ?", (kw.strip().lower(),))
    conn.commit()
    conn.close()

# --- NEGATIVE KEYWORDS ---
def get_negative_keywords():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT palavra FROM negative_keywords ORDER BY palavra ASC")
    kws = [row[0] for row in c.fetchall()]
    conn.close()
    return kws

def add_negative_keyword(kw: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO negative_keywords (palavra) VALUES (?)", (kw.strip().lower(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_negative_keyword(kw: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM negative_keywords WHERE palavra = ?", (kw.strip().lower(),))
    conn.commit()
    conn.close()

# --- CONFIGURAÇÕES GERAIS ---
def get_config(chave: str) -> str:
    """Busca o valor string de uma configuração. Retorna string vazia se não achar."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def set_config(chave: str, valor: str):
    """Atualiza ou insere uma configuração."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO config (chave, valor) 
        VALUES (?, ?) 
        ON CONFLICT(chave) 
        DO UPDATE SET valor=excluded.valor
    ''', (chave, str(valor)))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE HISTÓRICO (DEDUPLICAÇÃO) ---
def check_duplicate(hash_id: str) -> bool:
    """Verifica se uma oferta com esse hash foi postada nos últimos 60 minutos."""
    import datetime
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Limpa registros antigos antes de checar (mais de 60 min)
    limite = (datetime.datetime.now() - datetime.timedelta(minutes=60)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("DELETE FROM history WHERE posted_at < ?", (limite,))
    
    c.execute("SELECT 1 FROM history WHERE hash_id = ?", (hash_id,))
    res = c.fetchone()
    conn.commit()
    conn.close()
    return res is not None

def add_to_history(hash_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO history (hash_id) VALUES (?)", (hash_id,))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE ADMINS ---
def get_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username FROM admins")
    rows = c.fetchall()
    conn.close()
    return rows

def add_admin(user_id: int, username: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO admins (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_admin(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

# --- FUNÇÕES DE SORTEIOS ---
def create_giveaway(premio: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sorteios (premio) VALUES (?)", (premio,))
    conn.commit()
    conn.close()

def get_active_giveaways():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, premio FROM sorteios WHERE status = 'aberto'")
    rows = c.fetchall()
    conn.close()
    return rows

def close_giveaway(giveaway_id: int, winner_id: int, winner_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE sorteios SET status = 'encerrado', ganhador_id = ?, ganhador_nome = ? WHERE id = ?", 
              (winner_id, winner_name, giveaway_id))
    conn.commit()
    conn.close()

# Aliases para compatibilidade com o literalmente_bot
get_active_sorteios = get_active_giveaways
create_sorteio = create_giveaway
finalize_sorteio = close_giveaway

# Inicializa o banco ao importar
init_db()
