import asyncio
import os
import re
import hashlib
from telethon import TelegramClient, events, utils
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import ChannelInvalidError, UsernameInvalidError
from config import API_ID, API_HASH, TARGET_CHANNEL
from database import get_canais, get_keywords, get_config, check_duplicate, add_to_history, get_negative_keywords, normalize_channel

from rewriter import reescrever_promocao
from links import process_and_replace_links, extract_urls, expand_url
from publisher import publish_deal, bot
from watermark import apply_watermark
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from whatsapp_publisher import send_whatsapp_msg

# O ADMIN_USER_ID agora é recuperado do banco de dados (chave 'admin_id')

# Variável global para armazenar as ofertas que aguardam aprovação manual
ofertas_pendentes_admin = []

# Certifique-se de que o diretório de downloads existe
base_downloads_path = "downloads"
if not os.path.exists(base_downloads_path):
    os.makedirs(base_downloads_path)

from telethon.sessions import StringSession
import logging

session_str = os.getenv("TELEGRAM_STRING_SESSION")
if session_str:
    print(f"📡 StringSession detectada (Início: {session_str[:15]}...)")
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
else:
    print("📁 Usando sessão via arquivo local (literalmente_userbot.session)")
    client = TelegramClient('literalmente_userbot', API_ID, API_HASH)

# Fila para gerenciar o delay e as postagens
post_queue = asyncio.Queue()

def debug_log(message):
    """Loga mensagens apenas se o modo debug estiver ativo."""
    if get_config("debug_mode") == "1":
        print(f"[DEBUG] {message}")

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

# Cache global para IDs dos canais monitorados
monitored_ids_cache = {}

async def resolve_monitored_channels():
    """Resolve os IDs de todos os canais no banco de dados para o cache de monitoramento."""
    global monitored_ids_cache
    source_channels = get_canais()
    new_cache = {}
    print(f"🔍 Atualizando cache de IDs para {len(source_channels)} canais...")
    
    for channel in source_channels:
        try:
            channel_name = normalize_channel(channel)
            entity = await client.get_entity(channel_name)
            peer_id = utils.get_peer_id(entity)
            new_cache[peer_id] = channel_name.lower()
            print(f"✅ ID Resolvido: @{channel_name} -> {peer_id}")
        except Exception as e:
            print(f"⚠️ Não foi possível resolver ID para {channel}: {e}")
            
    monitored_ids_cache = new_cache
    print(f"✨ Cache atualizado com {len(monitored_ids_cache)} IDs.")

async def ensure_joined_channels():
    """Garante que o Userbot está participando de todos os canais monitorados."""
    source_channels = get_canais()
    print(f"📋 Verificando filiação em {len(source_channels)} canais...")
    
    for channel in source_channels:
        try:
            # Normaliza e tenta entrar
            channel_name = normalize_channel(channel)
            print(f"🔗 Verificando canal: {channel_name}...")
            await client(JoinChannelRequest(channel_name))
            print(f"✅ Userbot garantido no canal: {channel_name}")
        except (ChannelInvalidError, UsernameInvalidError):
            print(f"⚠️ Erro: Canal ou Username inválido: {channel}")
        except Exception as e:
            if "already a participant" in str(e).lower():
                print(f"ℹ️ Userbot já participa do canal: {channel}")
            else:
                print(f"⚠️ Erro ao entrar no canal {channel}: {e}")
    
    # Após entrar, resolvemos os IDs para o cache
    await resolve_monitored_channels()

async def start_monitoring():
    source_channels = get_canais()
    
    # Inicia o worker em background
    asyncio.create_task(worker_queue())
    
    print("⏳ Conectando o Userbot ao Telegram...")
    try:
        # Tenta conectar com timeout para não travar o loop se houver problema de rede/proxy
        await asyncio.wait_for(client.connect(), timeout=30)
    except asyncio.TimeoutError:
        print("⚠️ Erro: Timeout ao conectar ao Telegram. Verifique sua conexão.")
        return
    except Exception as e:
        print(f"⚠️ Erro ao conectar ao Telegram: {e}")
        return
    
    try:
        if not await client.is_user_authorized():
            print("\n" + "!"*60)
            print("❌ ERRO FATAL: O Userbot não está autorizado ou a sessão foi revogada!")
            print("💡 Motivo Provável: Conflito de IPs ou StringSession expirada.")
            print("🛠️ RESOLUÇÃO:")
            print("1. Rode 'python get_string.py' localmente para gerar uma nova sessão.")
            print("2. Atualize a variável TELEGRAM_STRING_SESSION na Square Cloud.")
            print("3. Reinicie o bot e NÃO rode o bot localmente enquanto ele estiver na nuvem.")
            print("!"*60 + "\n")
            return
    except Exception as e:
        err_msg = str(e).lower()
        print(f"⚠️ Erro ao verificar autorização: {e}")
        
        if "simultaneously" in err_msg or "revoked" in err_msg or "expired" in err_msg:
            print("🚨 CONFLITO CRÍTICO DE SESSÃO DETECTADO!")
            print("Tentando remover arquivo de sessão local para forçar novo login via StringSession...")
            try:
                # O Telethon trava o arquivo .session. Precisamos desconectar antes de renomear.
                await client.disconnect()
                if os.path.exists("literalmente_userbot.session"):
                    backup_name = f"literalmente_userbot.session.old_{int(asyncio.get_event_loop().time())}"
                    os.rename("literalmente_userbot.session", backup_name)
                    print(f"✅ Arquivo de sessão renomeado para: {backup_name}")
            except Exception as rename_err:
                print(f"❌ Não foi possível limpar o arquivo de sessão: {rename_err}")
            
            print("⏸️ Aguardando 5 minutos antes de reiniciar o processo para evitar Flood...")
            await asyncio.sleep(300) # 5 minutos para acalmar os ânimos do Telegram
        return

    print("✅ Userbot conectado e autorizado!")
    
    # Executa o auto-join
    await ensure_joined_channels()
    
    print(f"✅ Monitoramento iniciado! Canais no Banco: {source_channels}")
    
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
            chat_title = getattr(chat, 'title', 'Sem Título')
            chat_username = getattr(chat, 'username', 'N/A')
            chat_id = event.chat_id
            debug_log(f"Mensagem recebida de '{chat_title}' (@{chat_username}) [ID: {chat_id}]")
            
            is_monitored = False
            
            # Check por ID (mais confiável)
            if chat_id in monitored_ids_cache:
                is_monitored = True
            else:
                # Fallback por Username (caso o cache esteja desatualizado)
                monitored_list = [normalize_channel(c).lower() for c in get_canais()]
                if chat_username and chat_username.lower() in monitored_list:
                    is_monitored = True
                    # Aproveita para atualizar o cache
                    monitored_ids_cache[chat_id] = chat_username.lower()
                elif str(chat_id) in monitored_list:
                    is_monitored = True
                
            if not is_monitored:
                return

            print(f"🎯 MENSAGEM DE CANAL MONITORADO: '{chat_title}' (@{chat_username}) [ID: {chat_id}]")

            

            # Verifica se o bot está pausado globalmente
            if get_config("pausado") == "1":
                debug_log("Bot pausado globalmente.")
                return
                
            # Verifica mensagens já processadas pelo ID exato
            if event.message.id in processed_message_ids:
                debug_log(f"Mensagem já processada ignorada (ID: {event.message.id})")
                return
            processed_message_ids.add(event.message.id)
            if len(processed_message_ids) > 1000:
                processed_message_ids.clear()
                
            # --- FILTRO DE MÍDIA (Urgente: Apenas Texto ou Foto) ---
            if event.message.media:
                from telethon.tl.types import MessageMediaPhoto
                if not isinstance(event.message.media, MessageMediaPhoto):
                    debug_log(f"🚫 Ignorado: Mídia do tipo '{type(event.message.media).__name__}' não permitida (Apenas fotos/texto).")
                    return

            # Verifica se a mensagem faz parte de um álbum já processado
            if event.message.grouped_id:
                if event.message.grouped_id in processed_grouped_ids:
                    debug_log(f"Mensagem extra do mesmo álbum ignorada: {event.message.grouped_id}")
                    return
                processed_grouped_ids.add(event.message.grouped_id)
                # Mantém o set pequeno
                if len(processed_grouped_ids) > 500:
                    processed_grouped_ids.clear()
                
            print("\n" + "="*50)
            channel_name = chat_username or chat_id
            print(f"🚨 Nova mensagem identificada no canal fonte: {channel_name}")
            mensagem_texto = event.raw_text
            
            # Se a mensagem for só mídia ou mensagem vazia ignora
            if not mensagem_texto and not event.message.media:
                return

            # Verifica keywords negativas
            negative_keywords = get_negative_keywords()
            if negative_keywords and mensagem_texto:
                for n_kw in negative_keywords:
                    if n_kw.lower() in mensagem_texto.lower():
                        print(f"🚫 Ignorado: A mensagem contém a keyword negativa: '{n_kw}'")
                        print(f"📝 Texto analisado (trecho): {mensagem_texto[:100]}...")
                        return
                
            # Verifica as keywords (se a lista não for vazia)
            keywords = get_keywords()
            if keywords and mensagem_texto:
                has_keyword = any(kw.lower() in mensagem_texto.lower() for kw in keywords)
                if not has_keyword:
                    matched_none = True
                    print(f"⏭️ Ignorado: Nenhuma keyword encontrada. Texto analisado (trecho): {mensagem_texto[:100]}...")
                    print(f"🔍 Keywords configuradas: {', '.join(keywords)}")
                    return
                else:
                    found_kws = [kw for kw in keywords if kw.lower() in mensagem_texto.lower()]
                    print(f"✅ Keywords encontradas: {', '.join(found_kws)}")
                
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
                
            # --- DEDUPLICAÇÃO NO CANAL DESTINO ---
            # Tenta buscar o título exato via IA para evitar falsos positivos
            from rewriter import extrair_nome_produto
            titulo_real = await extrair_nome_produto(mensagem_texto)
            
            link_match = re.search(r'(https?://[^\s]+)', mensagem_texto)
            referencia = link_match.group(1).split('?')[0] if link_match else ""
            
            # Se a IA por algum motivo falhou em extrair um título claro
            if not titulo_real or titulo_real == "Oferta Desconhecida":
                if referencia:
                    # Se tiver link mas não tiver titulo, tenta resgatar por scraping em último caso
                    # Se for Shopee, tenta a API oficial primeiro para evitar block de scraper
                    from affiliate import get_shopee_product_info
                    shopee_info = None
                    if "shopee.com.br" in referencia:
                        shopee_info = await get_shopee_product_info(referencia)
                    
                    if shopee_info and shopee_info.get("title"):
                        titulo_real = shopee_info["title"]
                        print(f"✅ Titulo Shopee obtido via API: {titulo_real}")
                    else:
                        from scraper import fetch_product_metadata
                        try:
                            metadata = await fetch_product_metadata(referencia)
                            if metadata and metadata.get("title"):
                                titulo_real = metadata["title"].strip()
                        except Exception as e:
                            print(f"⚠️ Erro no scraper de fallback: {e}")
                
            # Se ainda assim não tiver, vai pra primeira linha
            if not titulo_real or titulo_real == "Oferta Desconhecida":
                if referencia:
                    titulo_real = referencia
                else:
                    primeira_linha = mensagem_texto.split('\n')[0].strip()
                    titulo_real = re.sub(r'[^\w\s]', '', primeira_linha).strip().lower()[:50]
            
            # Pega o primeiro valor R$ achado (ou 0 se não houver)
            todos_precos = re.findall(r'R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', mensagem_texto)
            valor_referencia = todos_precos[0] if todos_precos else "0"
            valor_referencia_limpo = valor_referencia.replace('.', '').replace(',', '.')
            
            # Busca no histórico recente do canal destino
            print(f"🔍 Verificando duplicidade no canal de destino ({TARGET_CHANNEL})... Buscando: '{titulo_real}' e 'R$ {valor_referencia}'")
            oferta_duplicada = False
            try:
                # Retorna mensagens das últimas 1 hora (60 minutos) usando o telethon client iter_messages
                from datetime import datetime, timedelta, timezone
                time_threshold = datetime.now(timezone.utc) - timedelta(minutes=60)
                
                async for past_msg in client.iter_messages(TARGET_CHANNEL, offset_date=datetime.now(timezone.utc)):
                    if past_msg.date < time_threshold:
                        break # Só checa a última hora
                    
                    if past_msg.text:
                        # Limpa o texto passado e o titulo real pesquisado para fazer match case-insensitive e sem acentos de forma basica
                        past_text_lower = past_msg.text.lower()
                        titulo_pesquisa_lower = titulo_real.lower()
                        
                        # Precisa achar palavras-chave do título e o valor exato no post do canal destino
                        # Dividimos o titulo real pesquisado em tokens
                        tokens_titulo = [t for t in titulo_pesquisa_lower.split() if len(t) > 3]
                        
                        # Match 1: O valor numérico precisa estar no post
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
                             # Se o titulo for só uma short string (ou link), busca raw match
                             if titulo_pesquisa_lower in past_text_lower:
                                  teve_match_titulo = True
                                  
                        if teve_match_valor and teve_match_titulo:
                            oferta_duplicada = True
                            print(f"🛑 Post ignorado: Exatamente este produto '{titulo_real}' por R$ {valor_referencia} já foi postado no canal de destino nos últimos 60 minutos.")
                            
                            admin_id_str = get_config("admin_id")
                            if admin_id_str:
                                try:
                                    msg_info = f"🚫 **Post Ignorado por Duplicação no {TARGET_CHANNEL}**\nO produto *{titulo_real}* por R$ {valor_referencia} já foi anunciado pelo robô há menos de 60 minutos."
                                    await bot.send_message(chat_id=int(admin_id_str), text=msg_info, parse_mode="Markdown")
                                except: pass
                            break
                            
            except Exception as e:
                print(f"⚠️ Erro ao verificar histórico do canal de destino: {e}")
                
            if oferta_duplicada:
                return

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
                try:
                    msg_info = f"🔎 **Nova oferta detectada!**\nCanal: `{getattr(event.chat, 'title', None) or chat_id}`\n📥 [Postagem Original]({source_url})\n⏳ Processando publicação..."
                    await bot.send_message(chat_id=int(admin_id_str), text=msg_info, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception as e:
                    print(f"Erro ao notificar admin sobre detecção: {e}")
            
            # --- FASE 0: Extrair Mídia (Telegram ou Scraper) ---
            media_path = None
            source_has_media = bool(event.message.media)
            
            # Tenta baixar a mídia do Telegram primeiro (fallback)
            if source_has_media:
                print("⏬ Baixando mídia do Telegram...")
                media_path = await event.message.download_media(file="downloads/")
                print(f"✅ Mídia do Telegram baixada: {media_path}")

            # --- FASE 1: Extrair, Remover e Processar Links (Conversão e Expansão) ---
            print("🔗 Processando links e substituindo por placeholders...")
            
            # Extrair links de botões (Inline Keyboard) do canal original
            original_button_links = []
            if event.message.reply_markup:
                from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonUrl
                if isinstance(event.message.reply_markup, ReplyInlineMarkup):
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            if isinstance(button, KeyboardButtonUrl):
                                original_button_links.append(button.url)
                                print(f"🔘 Link de botão detectado: {button.url}")

            # Identificar o primeiro link de produto para tentar pegar imagem limpa
            primeiro_link_produto = None
            all_source_urls = extract_urls(mensagem_texto) + original_button_links
            if all_source_urls:
                # Pega o primeiro link que pareça de uma loja
                for l in all_source_urls:
                    if any(store in l.lower() for store in ["amazon", "mercadolivre", "shopee", "magazineluiza", "casasbahia"]):
                        primeiro_link_produto = l
                        break

            # Se achamos um link de produto, tentamos pegar a imagem limpa da loja
            if primeiro_link_produto:
                print(f"🔍 Tentando buscar imagem limpa da loja: {primeiro_link_produto}")
                from affiliate import get_shopee_product_info
                shopee_info = None
                if "shopee.com.br" in primeiro_link_produto:
                    shopee_info = await get_shopee_product_info(primeiro_link_produto)
                
                if shopee_info and shopee_info.get("image"):
                    from scraper import download_image
                    temp_clean_path = await download_image(shopee_info["image"])
                    if temp_clean_path:
                        print(f"📸 Imagem Shopee obtida via API: {temp_clean_path}")
                        if media_path and os.path.exists(media_path):
                            try: os.remove(media_path)
                            except: pass
                        media_path = temp_clean_path
                else:
                    from scraper import fetch_product_metadata
                    try:
                        # Expandir se necessário para o scraper funcionar melhor
                        expanded_for_img = await expand_url(primeiro_link_produto)
                        metadata = await fetch_product_metadata(expanded_for_img)
                        if metadata and metadata.get("local_image_path"):
                            temp_clean_path = metadata["local_image_path"]
                            print(f"📸 Imagem limpa encontrada na loja: {temp_clean_path}")
                            
                            # Se baixou a limpa, prioriza ela sobre a do Telegram
                            if media_path and os.path.exists(media_path):
                                try:
                                    os.remove(media_path)
                                except: pass
                            media_path = temp_clean_path
                            print("✨ Usando imagem original do site (limpa de logos do concorrente).")
                    except Exception as e:
                        print(f"⚠️ Falha ao tentar buscar imagem limpa: {e}")

            # Aplica a marca d'água (se houver imagem, seja do telegram ou do scraper)
            if media_path and os.path.exists(media_path):
                try:
                    from watermark import apply_watermark
                    media_path = apply_watermark(media_path)
                    print("🖌️ Marca d'água aplicada à imagem final.")
                except Exception as e:
                    print(f"⚠️ Não foi possível aplicar marca d'água: {e}")

            # Se houver links nos botões, vamos injetá-los no texto (no final) para que o bot os processe e crie nossos próprios botões
            texto_para_processar = mensagem_texto
            if original_button_links:
                # Adiciona os links dos botões ao final do texto para garantir que sejam capturados
                links_str = "\n".join(original_button_links)
                texto_para_processar += f"\n{links_str}"
                print(f"➕ {len(original_button_links)} links de botões adicionados ao texto para processamento.")

            texto_com_placeholders, placeholder_map = await process_and_replace_links(texto_para_processar)
            print(f"✅ {len(placeholder_map)} links encontrados no total.")

            # --- FILTRO DE QUALIDADE: Validar se há links de compra reais ---
            # Remove links do tipo YouTube ou Telegram de serem considerados "compra"
            valid_buy_links = {
                p: url for p, url in placeholder_map.items() 
                if url and not any(content in url.lower() for content in ["youtube.com", "youtu.be", "t.me", "chat.whatsapp.com"])
            }
            
            if not valid_buy_links:
                print("⏭️ Ignorado: Nenhum link de COMPRA válido encontrado (Apenas links de conteúdo ou vazios).")
                # Se baixou mídia, limpa
                if media_path and os.path.exists(media_path):
                    os.remove(media_path)
                return
            
            # --- FILTRO ADICIONAL: Palavras de "Conteúdo" sem indicação de oferta ---
            palavras_filtro_conteudo = ["análise completa", "testei o", "vídeo novo", "inscreva-se", "meu canal"]
            if any(p in mensagem_texto.lower() for p in palavras_filtro_conteudo) and len(valid_buy_links) < 1:
                # Caso extremo onde o link de compra é camuflado mas o texto é claramente um ad de vídeo
                print("⏭️ Ignorado: Texto identificado como promoção de conteúdo/vídeo.")
                if media_path and os.path.exists(media_path):
                    os.remove(media_path)
                return

            print(f"🛍️ {len(valid_buy_links)} links de compra reais identificados. Prosseguindo...")

            
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

    # Loop de reconexão persistente para evitar quedas por [Errno 104] (Connection reset by peer)
    while True:
        try:
            if not client.is_connected():
                await client.connect()
            await client.run_until_disconnected()
        except Exception as connection_error:
            print(f"⚠️ Aviso: Telethon desconectado. Reconectando em 10 segundos... Motivo: {connection_error}")
            await asyncio.sleep(10)

async def handle_manual_post(text, media=None):
    # Lógica para posts manuais via Mini App
    pass
