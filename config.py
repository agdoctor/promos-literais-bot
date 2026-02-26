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
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")
