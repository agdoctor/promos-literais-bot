import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Mercado Livre Affiliate Cookie
ML_AFFILIATE_COOKIE = os.getenv("ML_AFFILIATE_COOKIE")

# Amazon Affiliate Tag
AMAZON_TAG = os.getenv("AMAZON_TAG", "luiz4opromos-20")

# AliExpress Affiliate
ALI_APP_KEY = os.getenv("ALI_APP_KEY")
ALI_APP_SECRET = os.getenv("ALI_APP_SECRET")
ALI_TRACKING_ID = os.getenv("ALI_TRACKING_ID")

# Shopee Affiliate
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID")
SHOPEE_SOURCE_ID = os.getenv("SHOPEE_SOURCE_ID")
SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID")
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET")

# Proxy Configuration (Opcional - Recomendado para evitar 403)
PROXY_URL = os.getenv("PROXY_URL") or "http://yvqwihmq-1:wvd70499o3a5@p.webshare.io:80/"

# WhatsApp (Green-API - Lightweight)
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
GREEN_API_INSTANCE_ID = os.getenv("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")
GREEN_API_HOST = os.getenv("GREEN_API_HOST", "api.green-api.com")
WHATSAPP_DESTINATION = os.getenv("WHATSAPP_DESTINATION") # ID do Grupo ou Comunidade

# Tratar os canais, permitindo múltiplos separados por vírgula no futuro
SOURCE_CHANNELS = [c.strip() for c in os.getenv("SOURCE_CHANNELS", "").split(',') if c.strip()]
# Canais de destino (suporta múltiplos separados por vírgula)
_target_env = os.getenv("TARGET_CHANNELS") or os.getenv("TARGET_CHANNEL", "")
TARGET_CHANNELS = [c.strip() for c in _target_env.split(',') if c.strip()]
# Alias para compatibilidade com o código que espera apenas um canal (pega o primeiro)
TARGET_CHANNEL = TARGET_CHANNELS[0] if TARGET_CHANNELS else None

def get_target_channels():
    """Busca canais de destino de forma dinâmica (Prioridade: Banco > Env)."""
    try:
        from database import get_config
        db_val = get_config("target_channels")
        if db_val:
            return [c.strip() for c in db_val.split(',') if c.strip()]
    except Exception:
        pass
    
    # Fallback dinâmico para variáveis de ambiente
    _target_env = os.getenv("TARGET_CHANNELS") or os.getenv("TARGET_CHANNEL", "")
    if _target_env:
        return [c.strip() for c in _target_env.split(',') if c.strip()]
        
    return TARGET_CHANNELS
