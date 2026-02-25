import asyncio
import os
import sys
import io
import traceback
from datetime import datetime, timezone, timedelta

# Força o encoding do console do Windows/Docker para utf-8 para evitar UnicodeEncodeError global
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback para Python antigo
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except: pass

class LoggerWriter:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.filename = filename
        self.at_start = True

    def write(self, message):
        if not message or message == '\n': 
            try:
                self.terminal.write(message)
            except UnicodeEncodeError:
                self.terminal.write(message.encode(self.terminal.encoding, errors='backslashreplace').decode(self.terminal.encoding))
            return
            
        now = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("[%d/%m %H:%M:%S] ")
        formatted = ""
        lines = message.splitlines(keepends=True)
        for line in lines:
            if self.at_start and line.strip():
                formatted += now
                self.at_start = False
            formatted += line
            if line.endswith('\n'):
                self.at_start = True
        
        try:
            self.terminal.write(formatted)
        except UnicodeEncodeError:
            # Fallback para terminais que não suportam certos caracteres
            self.terminal.write(formatted.encode(self.terminal.encoding, errors='backslashreplace').decode(self.terminal.encoding))
            
        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(formatted)
        except: pass

    def flush(self):
        self.terminal.flush()

sys.stdout = LoggerWriter("bot.log")
sys.stderr = sys.stdout

async def run_task_with_retry(name, coro_func, delay=10):
    """Executa uma tarefa e a reinicia em caso de erro fatal."""
    while True:
        try:
            print(f"🚀 Iniciando: {name}")
            await coro_func()
            print(f"ℹ️ {name} finalizado voluntariamente.")
            break 
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ Erro em {name}: {e}")
            traceback.print_exc()
            print(f"🔄 Reiniciando {name} em {delay}s...")
            await asyncio.sleep(delay)

async def main():
    print("="*50)
    print("INICIANDO SISTEMA LITERALMENTE PROMO")
    print("="*50)
    
    # Banco de dados
    from database import init_db
    init_db()

    # Imports locais para evitar circular dependency
    from web_dashboard import start_web_server
    from monitor import start_monitoring
    from admin import start_admin_bot

    # Criamos as tarefas
    dashboard_task = asyncio.create_task(run_task_with_retry("Dashboard Web", start_web_server, delay=5))
    await asyncio.sleep(2)
    monitor_task = asyncio.create_task(run_task_with_retry("Monitoramento", start_monitoring, delay=20))
    admin_task = asyncio.create_task(run_task_with_retry("Bot Admin", start_admin_bot, delay=10))
    
    tasks = [dashboard_task, monitor_task, admin_task]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("Finalizando...")
        for t in tasks: t.cancel()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
