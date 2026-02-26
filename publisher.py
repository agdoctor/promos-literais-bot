import asyncio
import os
import re
import hashlib
import time
from aiogram import Bot
from aiogram.types import FSInputFile
from config import BOT_TOKEN, TARGET_CHANNEL

# Inicializa o Bot do aiogram (apenas para envio de mensagens, sem polling)
try:
    bot = Bot(token=BOT_TOKEN)
except Exception as e:
    print(f"Erro ao inicializar o Bot: {e}")
    bot = None

async def send_with_retry(coro_maker):
    """Executa enviando a mensagem com retry automatico pra FloodWait e erros de conexao."""
    for attempt in range(4): # Aumentado para 4 tentativas (original 3 + 1 final)
        try:
            return await coro_maker()
        except Exception as e:
            err_str = str(e).lower()
            
            # 1. Tratar FloodWait (Rate limit do Telegram)
            if "retry after" in err_str:
                import re
                match = re.search(r'retry after (\d+)', err_str)
                wait_sec = int(match.group(1)) if match else 5
                print(f"[Telegram FloodWait] Aguardando {wait_sec} segundos...")
                await asyncio.sleep(wait_sec)
                
            # 2. Tratar Erros de Conexao (ex: Connection Reset by Peer - Errno 104)
            elif any(kw in err_str for kw in ["connection reset", "clientoserror", "errno 104", "server disconnected"]):
                wait_sec = (attempt + 1) * 2 # Backoff simples: 2s, 4s, 6s...
                print(f"[Telegram Erro de Conexao] {err_str[:50]}... Tentativa {attempt + 1}/4. Reconectando em {wait_sec}s...")
                await asyncio.sleep(wait_sec)
                
            else:
                # Outros erros (ex: Bad Request) nao devem ser repetidos cegamente
                raise e
                
    return await coro_maker()

async def publish_deal(text: str, media_path: str | None = None, reply_markup = None):
    """
    Publica a oferta processada no canal oficial.
    """
    if not bot:
        print("[ERR] Bot nao configurado corretamente.")
        return

    try:
        print(f"[Publisher] Publicando oferta no canal {TARGET_CHANNEL}...")
        
        # O Telegram tem um limite de 1024 caracteres para legendas de fotos.
        is_long_text = len(text) > 1024
        sent_msg = None
        
        if media_path and not is_long_text and os.path.exists(media_path):
            try:
                sent_msg = await send_with_retry(lambda: bot.send_photo(chat_id=TARGET_CHANNEL, photo=FSInputFile(media_path), caption=text, parse_mode="HTML", reply_markup=reply_markup))
            except Exception as e:
                err_str = str(e).lower()
                if "parse" in err_str or "entities" in err_str or "bad request" in err_str:
                    print(f"[Telegram] Erro de HTML: {e}. Tentando sem formatacao...")
                    sent_msg = await send_with_retry(lambda: bot.send_photo(chat_id=TARGET_CHANNEL, photo=FSInputFile(media_path), caption=text, reply_markup=reply_markup))
                else:
                    raise e
        else:
            photo_msg = None
            if media_path and os.path.exists(media_path):
                photo_msg = await send_with_retry(lambda: bot.send_photo(chat_id=TARGET_CHANNEL, photo=FSInputFile(media_path)))
                await asyncio.sleep(0.5)
            
            try:
                sent_msg = await send_with_retry(lambda: bot.send_message(chat_id=TARGET_CHANNEL, text=text, disable_web_page_preview=True, parse_mode="HTML", reply_markup=reply_markup))
            except Exception as e:
                err_str = str(e).lower()
                if "parse" in err_str or "entities" in err_str or "bad request" in err_str:
                    print(f"[Telegram] Erro de HTML no texto: {e}. Tentando sem formatacao...")
                    try:
                        sent_msg = await send_with_retry(lambda: bot.send_message(chat_id=TARGET_CHANNEL, text=text, disable_web_page_preview=True, reply_markup=reply_markup))
                    except Exception as fallback_e:
                        if photo_msg:
                            try: await bot.delete_message(chat_id=TARGET_CHANNEL, message_id=photo_msg.message_id)
                            except: pass
                        raise fallback_e
                else:
                    if photo_msg:
                        try: await bot.delete_message(chat_id=TARGET_CHANNEL, message_id=photo_msg.message_id)
                        except: pass
                    raise e
            
        print("[OK] Oferta publicada com sucesso no seu canal!")
        
        target_url = ""
        if str(TARGET_CHANNEL).startswith("-100"):
            target_url = f"https://t.me/c/{str(TARGET_CHANNEL).replace('-100', '')}/{sent_msg.message_id}"
        elif str(TARGET_CHANNEL).startswith("@"):
            target_url = f"https://t.me/{str(TARGET_CHANNEL).replace('@', '')}/{sent_msg.message_id}"
        else:
            target_url = f"https://t.me/{str(TARGET_CHANNEL)}/{sent_msg.message_id}"
            
        return target_url
        
    except Exception as e:
        print(f"[ERR] Erro ao publicar via Bot: {e}")
        return None
