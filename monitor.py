import asyncio
import os
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import API_ID, API_HASH, TARGET_CHANNEL
from database import get_canais, get_keywords, get_config, check_duplicate, add_to_history, get_negative_keywords

from rewriter import reescrever_promocao, extrair_nome_produto
from links import process_and_replace_links, extract_urls
from scraper import extract_price, fetch_product_metadata
from telethon.errors import AuthKeyDuplicatedError
from datetime import datetime, timedelta, timezone
from publisher import publish_deal, bot
from watermark import apply_watermark
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from whatsapp_publisher import send_whatsapp_msg

# O ADMIN_USER_ID agora é recuperado do banco de dados (chave 'admin_id')

# Variável global para armazenar as ofertas que aguardam aprovação manual
ofertas_pendentes_admin = []

# Certifique-se de que o diretório de downloads existe com caminho absoluto
base_downloads_path = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(base_downloads_path):
    os.makedirs(base_downloads_path)

# Configuração da Sessão (Suporte a StringSession para Square Cloud)
session_str = os.getenv("TELEGRAM_STRING_SESSION")
if session_str:
    print(f"📡 StringSession detectada (Início: {session_str[:15]}...)")
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
else:
    print("📁 Usando sessão via arquivo local (literalmente_userbot.session)")
    client = TelegramClient('literalmente_userbot', API_ID, API_HASH)

# Fila para gerenciar o delay e as postagens
post_queue = asyncio.Queue()

async def worker_queue():
    """Worker que fica rodando em background consumindo a fila e aplicando o delay"""
    while True:
        try:
            item = await post_queue.get()
            
            # Suporta diferentes tamanhos da tupla
            if len(item) == 4:
                texto_final, media_path, reply_markup, source_url = item
            elif len(item) == 3:
                texto_final, media_path, reply_markup = item
                source_url = None
            else:
                texto_final, media_path = item
                reply_markup = None
                source_url = None
            
            delay_str = get_config("delay_minutos") or "0"
            try:
                delay_mins = float(delay_str)
            except:
                delay_mins = 0
                
            if delay_mins > 0:
                print(f"⏳ Delay ativado. Aguardando {delay_mins} minutos antes de publicar...")
                await asyncio.sleep(delay_mins * 60)
            
            print("📤 Worker publicando oferta da fila...")
            target_url = await publish_deal(texto_final, media_path, reply_markup=reply_markup)
            
            # --- Notificação de Conclusão ---
            admin_id_str = get_config("admin_id")
            if admin_id_str and target_url:
                try:
                    msg_conclusao = "✅ **Oferta Publicada com Sucesso!**\n\n"
                    if source_url:
                        msg_conclusao += f"📥 [Fonte Original]({source_url})\n"
                    msg_conclusao += f"📤 [Postagem no Canal]({target_url})"
                    
                    if media_path and os.path.exists(media_path):
                        from aiogram.types import FSInputFile
                        photo = FSInputFile(media_path)
                        await bot.send_photo(chat_id=int(admin_id_str), photo=photo, caption=msg_conclusao, parse_mode="Markdown")
                    else:
                        await bot.send_message(chat_id=int(admin_id_str), text=msg_conclusao, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception as e:
                    print(f"Aviso ao notificar admin na conclusao: {e}")
            
            # Adiciona ao histórico para evitar duplicatas (usamos o texto final como base)
            # Título e valor são extraídos de forma simplificada para o histórico
            # No worker, temos o texto_final pronto.
            titulo_clean = texto_final.split('\n')[0].replace('🛒', '').strip()
            valor_clean = extract_price(texto_final) or "0"
            add_to_history(titulo_clean, valor_clean)
            
            # --- Envio para WhatsApp (Se habilitado) ---
            try:
                from whatsapp_publisher import send_whatsapp_msg, format_whatsapp_text
                msg_wa = format_whatsapp_text(texto_final)
                send_whatsapp_msg(msg_wa, media_path)
            except Exception as e:
                print(f"Erro ao disparar para WhatsApp: {e}")
            
            # Limpar a mídia local depois de publicar de verdade
            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                    print("🗑️ Mídia local apagada.")
                except Exception as e:
                    print(f"Não foi possível apagar arquivo: {e}")
                    
            post_queue.task_done()
        except Exception as e:
            print(f"Erro no worker de fila: {e}")
            await asyncio.sleep(5)

async def start_monitoring():
    source_channels = get_canais()
    
    # Inicia o worker em background
    asyncio.create_task(worker_queue())
    
    print("⏳ Conectando o Userbot ao Telegram...")
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ ERRO FATAL: O Userbot não está autorizado! A StringSession fornecida é inválida ou expirou.")
        print("💡 Tente gerar uma nova StringSession localmente e atualize a variável na Square Cloud.")
        return

    print("✅ Userbot conectado e autorizado!")
    
    print(f"✅ Userbot conectado! Monitorando do Banco de Dados: {source_channels}")
    
    # Cache para não processar o mesmo álbum (várias fotos) duas vezes
    processed_grouped_ids = set()
    # Cache para não processar a mesma mensagem duas vezes (ex: edições rápidas ou múltiplos triggers do Telethon)
    processed_message_ids = set()
    
    @client.on(events.NewMessage())
    async def new_message_handler(event):
        try:
            # Verifica se o canal está na lista monitorada (vinda do banco de dados)
            source_channels = get_canais()
            
            # Identificadores possíveis: @username ou ID numérico (como string ou int)
            chat = await event.get_chat()
            chat_username = getattr(chat, 'username', None)
            chat_id = str(event.chat_id)
            
            is_monitored = False
            if chat_username and chat_username.lower() in [c.lower().replace('@', '') for c in source_channels]:
                is_monitored = True
            elif chat_id in source_channels or str(event.chat_id) in source_channels:
                is_monitored = True
                
            if not is_monitored:
                return

            # Verifica se o bot está pausado globalmente
            if get_config("pausado") == "1":
                return
                
            # Verifica mensagens já processadas pelo ID exato
            if event.message.id in processed_message_ids:
                print(f"⏭️ Mensagem já processada ignorada (ID: {event.message.id})")
                return
            processed_message_ids.add(event.message.id)
            if len(processed_message_ids) > 1000:
                processed_message_ids.clear()
                
            # Verifica se a mensagem faz parte de um álbum já processado
            if event.message.grouped_id:
                if event.message.grouped_id in processed_grouped_ids:
                    print(f"⏭️ Mensagem extra do mesmo álbum ignorada: {event.message.grouped_id}")
                    return
                processed_grouped_ids.add(event.message.grouped_id)
                # Mantém o set pequeno
                if len(processed_grouped_ids) > 500:
                    processed_grouped_ids.clear()
                
            print("\n" + "="*50)
            print("🚨 Nova mensagem identificada no canal fonte!")
            mensagem_texto = event.raw_text
            
            # Se a mensagem for só mídia ou mensagem vazia ignora
            if not mensagem_texto and not event.message.media:
                return

            # Verifica keywords negativas
            negative_keywords = get_negative_keywords()
            if negative_keywords:
                has_negative = any(n_kw.lower() in mensagem_texto.lower() for n_kw in negative_keywords)
                if has_negative:
                    print(f"🚫 Ignorado: A mensagem contém uma keyword negativa.")
                    return
                
            # Verifica as keywords (se a lista não for vazia)
            keywords = get_keywords()
            if keywords:
                has_keyword = any(kw.lower() in mensagem_texto.lower() for kw in keywords)
                if not has_keyword:
                    print("⏭️ Ignorado: Nenhuma keyword configurada foi encontrada no texto.")
                    return
                
            # Verifica Preço Mínimo (Se houver $ / R$ no texto)
            preco_min = float(get_config("preco_minimo") or "0")
            if preco_min > 0:
                # Busca valores obrigatoriamente procedidos por R$
                valores_encontrados = re.findall(r'R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', mensagem_texto)
                if valores_encontrados:
                    # Converte o primeiro valor achado pra float
                    str_valor = valores_encontrados[0].replace('.', '').replace(',', '.')
                    try:
                        valor_num = float(str_valor)
                        if valor_num < preco_min:
                            print(f"🛑 Ignorado por Filtro de Preço: R${valor_num:.2f} é menor que mínimo R${preco_min:.2f}")
                            return
                    except:
                        pass
                

            # --- NOTIFICAÇÃO ADMIN ---
            admin_id_str = get_config("admin_id")
            
            # Tenta gerar o link da postagem original
            source_url = ""
            chat_username_for_link = getattr(event.chat, 'username', None)
            if chat_username_for_link:
                source_url = f"https://t.me/{chat_username_for_link}/{event.message.id}"
            else:
                source_url = f"https://t.me/c/{str(event.chat_id).replace('-100', '')}/{event.message.id}"
                
            if admin_id_str:
                pass
                # try:
                #     msg_info = f"🔎 **Nova oferta detectada!**\nCanal: `{event.chat.title or event.chat_id}`\n📥 [Postagem Original]({source_url})\n⏳ Processando publicação..."
                #     await bot.send_message(chat_id=int(admin_id_str), text=msg_info, parse_mode="Markdown", disable_web_page_preview=True)
                # except:
                #     pass
            
            # --- DEDUPLICAÇÃO NO CANAL DESTINO ---
            # Tenta buscar o título exato via IA para evitar falsos positivos
            titulo_real = await extrair_nome_produto(mensagem_texto)
            
            link_match = re.search(r'(https?://[^\s]+)', mensagem_texto)
            referencia = link_match.group(1).split('?')[0] if link_match else ""
            
            # Se a IA por algum motivo falhou em extrair um título claro
            if not titulo_real or titulo_real == "Oferta Desconhecida":
                if referencia:
                    # Se tiver link mas não tiver titulo, tenta resgatar por scraping em último caso
                    try:
                        metadata = await fetch_product_metadata(referencia)
                        if metadata and metadata.get("title"):
                            titulo_real = metadata["title"].strip()
                    except Exception as e:
                        print(f"⚠️ Erro no scraper de fallback no LP: {e}")
            
            # Se ainda assim não tiver, vai pra primeira linha
            if not titulo_real or titulo_real == "Oferta Desconhecida":
                if referencia:
                    titulo_real = referencia
                else:
                    primeira_linha = mensagem_texto.split('\n')[0].strip()
                    titulo_real = re.sub(r'[^\w\s]', '', primeira_linha).strip().lower()[:50]
                
            valor_orig = extract_price(mensagem_texto) or "0"
            valor_referencia_limpo = valor_orig.replace('.', '').replace(',', '.')
            
            # Busca no histórico recente do canal destino
            print(f"🔍 Verificando duplicidade no canal de destino ({TARGET_CHANNEL})... Buscando: '{titulo_real}' e 'R$ {valor_orig}'")
            oferta_duplicada = False
            try:
                # Retorna mensagens das últimas 1 hora (60 minutos) usando o telethon client iter_messages
                time_threshold = datetime.now(timezone.utc) - timedelta(minutes=60)
                
                async for past_msg in client.iter_messages(TARGET_CHANNEL, offset_date=datetime.now(timezone.utc)):
                    if past_msg.date < time_threshold:
                        break # Só checa a última hora
                    
                    if past_msg.text:
                        # Limpa o texto passado e o titulo real pesquisado
                        past_text_lower = past_msg.text.lower()
                        titulo_pesquisa_lower = titulo_real.lower()
                        
                        # Precisa achar palavras-chave do título e o valor exato no post do canal destino
                        tokens_titulo = [t for t in titulo_pesquisa_lower.split() if len(t) > 3]
                        
                        # Match 1: O valor numérico precisa estar no post
                        # Regex para capturar todos os valores R$ no historico
                        valor_encontrado_historico = re.findall(r'R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', past_text_lower)
                        valores_historico_limpos = [v.replace('.', '').replace(',', '.') for v in valor_encontrado_historico]
                        
                        teve_match_valor = valor_referencia_limpo in valores_historico_limpos
                        teve_match_titulo = False
                        
                        if tokens_titulo:
                            matches = sum(1 for t in tokens_titulo if t in past_text_lower)
                            # Se pelo menos 50% dos tokens do produto alvo estiverem no post destino
                            if matches / len(tokens_titulo) >= 0.5:
                                teve_match_titulo = True
                        else:
                             if titulo_pesquisa_lower in past_text_lower:
                                  teve_match_titulo = True
                                  
                        if teve_match_valor and teve_match_titulo:
                            oferta_duplicada = True
                            print(f"🛑 Post ignorado: Exatamente este produto '{titulo_real}' por R$ {valor_orig} já foi postado no canal de destino nos últimos 60 minutos.")
                            
                            admin_id_str = get_config("admin_id")
                            if admin_id_str:
                                try:
                                    msg_info = f"🚫 **Post Ignorado por Duplicação no {TARGET_CHANNEL}**\nO produto *{titulo_real}* por R$ {valor_orig} já foi anunciado pelo robô há menos de 60 minutos."
                                    await bot.send_message(chat_id=int(admin_id_str), text=msg_info, parse_mode="Markdown")
                                except: pass
                            break
                            
            except Exception as e:
                print(f"⚠️ Erro ao verificar histórico do canal de destino: {e}")
                
            if oferta_duplicada:
                return
            
            media_path = None
            if event.message.media:
                print("⏬ Baixando mídia associada...")
                try:
                    # Usa o caminho absoluto garantido
                    media_path = await event.message.download_media(file=base_downloads_path + os.path.sep)
                    if media_path:
                        print(f"✅ Mídia baixada: {media_path}")
                    else:
                        print("⚠️ Falha ao baixar mídia: Retornou None.")
                except Exception as e:
                    print(f"❌ Erro ao baixar mídia via Telethon: {e}")
                    media_path = None
                
                # Applica a marca d'água (se o arquivo watermark.png existir na raiz)
                try:
                    media_path = apply_watermark(media_path)
                    print("🖌️ Marca d'água aplicada à imagem.")
                except Exception as e:
                    print(f"⚠️ Não foi possível aplicar marca d'água: {e}")
            
            # --- FAIXA DE SEGURANÇA: Se não tem mídia, tenta extrair do link ---
            if not media_path:
                print("🔍 Mídia não encontrada na mensagem, tentando extrair do link...")
                urls_detectadas = extract_urls(mensagem_texto)
                if urls_detectadas:
                    # Tenta o primeiro link detectado
                    meta_fallback = await fetch_product_metadata(urls_detectadas[0])
                    media_path = meta_fallback.get("local_image_path")
                    if media_path:
                        print(f"✅ Mídia extraída via scraping: {media_path}")
                        try:
                            media_path = apply_watermark(media_path)
                        except: pass
            
            # --- FASE 1: Extrair, Remover e Processar Links (Conversão e Expansão) ---
            print("🔗 Processando links e substituindo por placeholders...")
            texto_com_placeholders, placeholder_map = await process_and_replace_links(mensagem_texto)
            print(f"✅ {len(placeholder_map)} links processados.")
            
            # --- FASE 2: Reescrever Texto com Gemini ---
            print("🧠 Passando para o Gemini reescrever a copy...")
            texto_reescrito = await reescrever_promocao(texto_com_placeholders)
            
            # --- FASE 3: Remontar o Texto Final Substituindo Placeholders ---
            texto_final = texto_reescrito
            
            if placeholder_map:
                for placeholder, final_url in placeholder_map.items():
                    # Se o link original era da blacklist ou deu erro e for None, ignoramos a formatação ou deletamos o placeholder
                    if final_url is None:
                        texto_final = texto_final.replace(placeholder, "")
                    else:
                        botao_html = f"🛒 <a href='{final_url}'>Pegar promoção</a>"
                        texto_final = texto_final.replace(placeholder, botao_html)
                        
            # Remove qualquer placeholder residual que o Gemini possa ter inventado
            texto_final = re.sub(r'\[LINK_\d+\]', '', texto_final)
                    
            # --- FASE 3.5: Adicionar Assinatura Customizada ---
            assinatura = get_config("assinatura")
            if assinatura:
                texto_final += f"\n\n{assinatura}"
            
            print("✅ Texto final pronto!")
            
            # --- FASE 4: Direcionamento (Aprovação, Fila ou Direto) ---
            admin_id_str = get_config("admin_id")
            if not admin_id_str:
                print("⚠️ Admin ID não configurado no banco. O administrador precisa dar /start no bot.")
                # Se não tem admin mas o bot deveria postar, vamos colocar na fila apenas se NÃO for manual
                if get_config("aprovacao_manual") != "1":
                    await post_queue.put((texto_final, media_path, None, source_url))
                return

            admin_id = int(admin_id_str)
            msg_amostra = f"**NOVA OFERTA ENCONTRADA!**\n\n{texto_final}"

            if get_config("aprovacao_manual") == "1":
                # Lógica de aprovação manual
                print(f"⚖️ Modo Aprovação Manual ativado. Enviando para o Admin {admin_id}...")
                
                # Salva a oferta para aprovação futura
                ofertas_pendentes_admin.append({"texto": texto_final, "media": media_path, "source_url": source_url})
                item_id = len(ofertas_pendentes_admin) - 1
                
                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Postar", callback_data=f"aprovar_{item_id}"),
                        InlineKeyboardButton(text="✏️ Editar", callback_data=f"editar_{item_id}"),
                        InlineKeyboardButton(text="❌ Descartar", callback_data=f"recusar_{item_id}")
                    ]
                ])

                if media_path:
                    photo = FSInputFile(media_path)
                    try:
                        await bot.send_photo(chat_id=admin_id, photo=photo, caption=msg_amostra, reply_markup=markup, parse_mode="HTML")
                    except Exception as e:
                        # Se falhar o html
                        await bot.send_photo(chat_id=admin_id, photo=photo, caption=msg_amostra[:1024], reply_markup=markup)
                else:
                    await bot.send_message(chat_id=admin_id, text=msg_amostra, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

            else:
                # Automático, joga na fila, o Worker dá o delay e posta
                print("📥 Enviando oferta para a fila de publicação...")
                await post_queue.put((texto_final, media_path, None, source_url))
            
        except Exception as e:
            print(f"❌ Erro ao processar mensagem: {e}")
            admin_id_str = get_config("admin_id")
            if admin_id_str:
                pass
                # try:
                #     await bot.send_message(chat_id=int(admin_id_str), text=f"⚠️ **Erro no Monitor (Literalmente):**\n`{str(e)[:500]}`", parse_mode="Markdown")
                # except:
                #     pass

    # Loop de reconexão persistente para evitar quedas por [Errno 104] (Connection reset by peer)
    while True:
        try:
            if not client.is_connected():
                await client.connect()
            await client.run_until_disconnected()
        except AuthKeyDuplicatedError as e:
            print(f"🛑🛑 AuthKeyDuplicatedError: A sessão (StringSession) foi revogada ou está sendo usada em outro lugar! CUIDADO COM BAN! Pausando por 5 MINUTOS... Erro: {e}")
            await asyncio.sleep(300) # Pausa gigantesca para evitar Flood Wait do Telegram
        except Exception as connection_error:
            print(f"⚠️ Aviso: Telethon desconectado. Reconectando em 10 segundos... Motivo: {connection_error}")
            await asyncio.sleep(10)
