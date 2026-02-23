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

# Proxy Configuration (Opcional - Recomendado para evitar 403)
PROXY_URL = os.getenv("PROXY_URL")

# Tratar os canais, permitindo múltiplos separados por vírgula no futuro
SOURCE_CHANNELS = [c.strip() for c in os.getenv("SOURCE_CHANNELS", "").split(',') if c.strip()]
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")
