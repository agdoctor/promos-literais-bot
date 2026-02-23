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
    
    # Tabela para configurações gerais do bot (Chave -> Valor)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')

    # Tabela de Administradores
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Histórico de ofertas para filtro de cooldown/duplicatas
    c.execute('''
        CREATE TABLE IF NOT EXISTS historico_ofertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            valor TEXT NOT NULL,
            timestamp INTEGER NOT NULL
        )
    ''')

    # Tabela de Sorteios
    c.execute('''
        CREATE TABLE IF NOT EXISTS sorteios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            premio TEXT NOT NULL,
            status TEXT DEFAULT 'ativo', -- 'ativo', 'finalizado'
            vencedor_id INTEGER,
            vencedor_nome TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
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
    except:
        pass
        
    conn.commit()
    conn.close()

# --- CANAIS ---
def get_canais():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT nome_ou_link FROM canais")
    canais = [row[0] for row in c.fetchall()]
    conn.close()
    return canais

def add_canal(nome: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO canais (nome_ou_link) VALUES (?)", (nome.strip(),))
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

# --- KEYWORDS ---
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

# --- ADMINS ---
def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    # Se a tabela estiver vazia, o primeiro que falar com o bot vira admin
    if not row:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM admins")
        count = c.fetchone()[0]
        conn.close()
        if count == 0:
            return True # Permite o primeiro admin
    return row is not None

def add_admin(user_id: int, username: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username FROM admins")
    rows = c.fetchall()
    conn.close()
    return rows

def remove_admin(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- HISTÓRICO DE OFERTAS (COOLDOWN) ---
def check_duplicate(titulo: str, valor: str, window_minutes: int = 60) -> bool:
    """Verifica se uma oferta similar foi postada nos últimos X minutos."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    limit_ts = int(time.time()) - (window_minutes * 60)
    
    # Busca por título idêntico ou valor idêntico no mesmo período
    # Para ser mais robusto, comparamos título E valor.
    c.execute('''
        SELECT id FROM historico_ofertas 
        WHERE titulo = ? AND valor = ? AND timestamp > ?
    ''', (titulo.strip(), valor.strip(), limit_ts))
    
    row = c.fetchone()
    conn.close()
    return row is not None

def add_to_history(titulo: str, valor: str):
    """Adiciona uma oferta ao histórico."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO historico_ofertas (titulo, valor, timestamp) 
        VALUES (?, ?, ?)
    ''', (titulo.strip(), valor.strip(), int(time.time())))
    conn.commit()
    conn.close()

# --- SORTEIOS ---
def create_sorteio(premio: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sorteios (premio) VALUES (?)", (premio,))
    conn.commit()
    conn.close()

def get_active_sorteios():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, premio, criado_em FROM sorteios WHERE status = 'ativo'")
    rows = c.fetchall()
    conn.close()
    return rows

def finalize_sorteio(sorteio_id: int, vencedor_id: int, vencedor_nome: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE sorteios 
        SET status = 'finalizado', vencedor_id = ?, vencedor_nome = ? 
        WHERE id = ?
    ''', (vencedor_id, vencedor_nome, sorteio_id))
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

# Inicializa o banco ao importar
init_db()
