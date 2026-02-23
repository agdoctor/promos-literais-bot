import os
from aiogram import Bot
from aiogram.types import FSInputFile
from config import BOT_TOKEN, TARGET_CHANNEL

# Inicializa o Bot do aiogram (apenas para envio de mensagens, sem polling)
try:
    bot = Bot(token=BOT_TOKEN)
except Exception as e:
    print(f"Erro ao inicializar o Bot: {e}")
    bot = None

async def publish_deal(text: str, media_path: str | None = None, reply_markup = None):
    """
    Publica a oferta processada no canal oficial.
    """
    if not bot:
        print("❌ Bot não configurado corretamente.")
        return

    try:
        print(f"🚀 Publicando oferta no canal {TARGET_CHANNEL}...")
        
        # O Telegram tem um limite de 1024 caracteres para legendas de fotos.
        is_long_text = len(text) > 1024
        
        if media_path and not is_long_text:
            photo = FSInputFile(media_path)
            sent_msg = await bot.send_photo(chat_id=TARGET_CHANNEL, photo=photo, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            # Se o texto for longo ou não houver mídia, enviamos como mensagem normal
            if media_path:
                photo = FSInputFile(media_path)
                await bot.send_photo(chat_id=TARGET_CHANNEL, photo=photo)
            # Desativa o preview do link (disable_web_page_preview=True) para evitar imagens duplas
            sent_msg = await bot.send_message(chat_id=TARGET_CHANNEL, text=text, disable_web_page_preview=True, parse_mode="HTML", reply_markup=reply_markup)
            
        print("✅ Oferta publicada com sucesso no seu canal!")
        
        target_url = ""
        if str(TARGET_CHANNEL).startswith("-100"):
            target_url = f"https://t.me/c/{str(TARGET_CHANNEL).replace('-100', '')}/{sent_msg.message_id}"
        else:
            target_url = f"https://t.me/{str(TARGET_CHANNEL).replace('@', '')}/{sent_msg.message_id}"
            
        return target_url
        
    except Exception as e:
        print(f"❌ Erro ao publicar via Bot: {e}")
    finally:
        # Importante fechar a sessão do aiohttp internamente no aiogram
        # await bot.session.close() - O Telethon e o Aiogram juntos podem precisar de gerencimento fino da session
        pass
