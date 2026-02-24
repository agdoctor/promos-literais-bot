import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Carrega as credenciais do .env
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

async def main():
    if not API_ID or not API_HASH:
        print("❌ API_ID ou API_HASH não encontrados no arquivo .env!")
        return

    print(f"📡 API_ID: {API_ID}")
    print("⏳ Iniciando cliente Telethon...")
    
    # Usa uma sessão temporária para gerar a string
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        print("\n" + "="*50)
        print("✅ STRING SESSION GERADA COM SUCESSO!")
        print("="*50)
        print("\nCOPIE A LINHA ABAIXO:\n")
        print(session_str)
        print("\n" + "="*50)
        print("💡 COMO USAR:")
        print("1. Copie o código acima.")
        print("2. Vá no Painel da Square Cloud.")
        print("3. Atualize a variável TELEGRAM_STRING_SESSION com este valor.")
        print("4. Reinicie o bot.")
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
