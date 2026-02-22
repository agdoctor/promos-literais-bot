import asyncio
from monitor import start_monitoring
from admin import start_admin_bot

async def main():
    print("="*60)
    print("🤖 Bot Literalmente Promo - Sistema de Monitoramento + Controle")
    print("="*60)
    
    try:
        # Roda os dois processos (Userbot Telethon + Admin Aiogram) juntos assincronamente
        await asyncio.gather(
            start_monitoring(),
            start_admin_bot()
        )
    except KeyboardInterrupt:
        print("\nDesligando sistema...")
    except Exception as e:
        print(f"\nErro fatal: {e}")

if __name__ == "__main__":
    asyncio.run(main())
