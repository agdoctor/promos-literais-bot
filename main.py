import asyncio
from monitor import start_monitoring
from admin import start_admin_bot

import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

class LoggerWriter:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = LoggerWriter("bot.log")
sys.stderr = sys.stdout

async def main():
    print("="*60)
    print("Bot Literalmente Promo - Sistema de Monitoramento + Controle")
    print("="*60)
    
    while True:
        tasks = []
        try:
            # Roda os processos juntos assincronamente
            from web_dashboard import start_web_server
            t1 = asyncio.create_task(start_monitoring())
            t2 = asyncio.create_task(start_admin_bot())
            t3 = asyncio.create_task(start_web_server())
            tasks = [t1, t2, t3]
            
            await asyncio.gather(*tasks)
            # Se gather terminar (o que não deve ocorrer normalmente), quebra o loop
            break
        except KeyboardInterrupt:
            print("\nDesligando sistema...")
            for t in tasks: t.cancel()
            break
        except Exception as e:
            print(f"\nErro fatal: {e}")
            print("⏳ Cancelando processos em segundo plano...")
            for t in tasks: t.cancel()
            print("⏳ Tentando reconectar em 5 segundos...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
