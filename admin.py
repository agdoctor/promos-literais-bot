from typing import Optional, Dict, Any
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from config import BOT_TOKEN
import database
from database import add_canal, get_canais, remove_canal, add_keyword, get_keywords, remove_keyword, get_config, set_config, is_admin, add_admin, get_admins, remove_admin, get_active_sorteios, create_sorteio, finalize_sorteio
import os
import sys
import asyncio
import re

# O ADMIN_USER_ID agora é recuperado dinamicamente do banco de dados 
# quando o usuário envia /start ou /admin

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Estados simples para a conversa
user_states: Dict[int, Optional[str]] = {}
user_temp_data: Dict[int, Dict[str, Any]] = {}

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Criar Oferta via Link", callback_data="menu_criar_link")
    builder.button(text="📺 Gerenciar Canais", callback_data="menu_canais")
    builder.button(text="🔑 Gerenciar Keywords", callback_data="menu_keywords")
    builder.button(text="⚙️ Configurações Gerais", callback_data="menu_config")
    builder.button(text="👥 Gerenciar Admins", callback_data="menu_admins")
    builder.button(text="🎁 Gerenciar Sorteios", callback_data="menu_sorteios")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start", "admin"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # Restrição de Admin
    if not is_admin(user_id):
        # Primeiro usuário vira admin automaticamente
        if not get_admins():
            add_admin(user_id, message.from_user.username)
        else:
            return

    # Salva o ID do admin no banco de dados para o monitor saber para quem mandar alertas
    set_config("admin_id", str(user_id))
    
    await message.answer(
        "🛠️ **Painel de Controle - Literalmente Promo**\n\n"
        "O que você deseja gerenciar?",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    # Remove qualquer teclado físico residual (Menu de acesso rápido desativado)
    # Enviamos uma mensagem temporária e apagamos na mesma hora para não poluir
    msg = await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
    try:
        await msg.delete()
    except:
        pass
        
    user_states[user_id] = None

@dp.message(Command("meuid"))
async def cmd_meuid(message: Message):
    await message.answer(f"Seu ID do Telegram é: <code>{message.from_user.id}</code>", parse_mode="HTML")

@dp.message(Command("enviar"))
async def cmd_enviar_shortcut(message: Message):
    if is_admin(message.from_user.id):
        await start_criar_oferta_msg(message)

@dp.message(Command("reiniciar"))
async def cmd_reiniciar(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🔄 **Reiniciando o bot...**\nAguarde alguns instantes para que o sistema o inicie novamente.")
    await asyncio.sleep(1)
    
    # Fecha conexões de forma segura para evitar Connection Reset Error no novo processo
    try:
        from publisher import bot
        await bot.session.close()
    except: pass
    try:
        from monitor import client as userbot
        await userbot.disconnect()
    except: pass
    
    os.execv(sys.executable, ['python'] + sys.argv)

async def start_criar_oferta_msg(message: Message):
    user_states[message.from_user.id] = "esperando_link_criacao"
    user_temp_data[message.from_user.id] = {}
    await message.answer("🔗 **Criador de Ofertas**\n\nPor favor, envie o **LINK** do produto que deseja anunciar (Ex: Amazon, Mercado Livre):")

# --- CRIAR OFERTA MANUAL ---
@dp.callback_query(F.data == "menu_criar_link")
async def start_criar_oferta(callback: CallbackQuery):
    await start_criar_oferta_msg(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "retry_scraping")
async def handle_retry_scraping(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_temp_data.get(user_id)
    if not data or not data.get("link"):
        await callback.answer("❌ Erro: Link não encontrado.")
        return
    
    await callback.message.edit_text("🔄 Tentando extrair novamente...")
    
    from scraper import fetch_product_metadata
    metadata = await fetch_product_metadata(data["link"])
    
    user_temp_data[user_id]["titulo"] = metadata.get("title", "")
    user_temp_data[user_id]["local_image_path"] = metadata.get("local_image_path", "")
    
    status = metadata.get("status_code", 200)
    titulo_achado = metadata.get('title')
    
    if status in [403, 503] or not titulo_achado:
        warn_msg = "⚠️ A Amazon ainda está bloqueando (Captcha).\n\n" if status in [403, 503] else "⚠️ Ainda não consegui extrair o título.\n\n"
        retry_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Tentar Mais uma Vez", callback_data="retry_scraping")]
        ])
        await callback.message.edit_text(f"{warn_msg}O bloqueio persiste. Digite o nome manualmente ou tente de novo:", reply_markup=retry_kb)
    else:
        user_states[user_id] = "esperando_preco_criacao"
        await callback.message.edit_text(f"✅ Sucesso na tentativa! Identifiquei: **{titulo_achado}**\n\nQual é o valor final da promoção? (Só números):")
    
    await callback.answer()

# --- CANAIS ---
@dp.callback_query(F.data == "menu_canais")
async def menu_canais(callback: CallbackQuery):
    canais = get_canais()
    texto = "📺 **Canais Monitorados:**\n" + "\n".join([f"- {c}" for c in canais])
    texto += "\n\nPara remover, clique no canal abaixo. Para adicionar, digite o @ ou link do canal no chat agora."
    
    builder = InlineKeyboardBuilder()
    for c in canais:
        builder.button(text=f"❌ {c}", callback_data=f"delcanal_{c}")
    builder.button(text="🔙 Voltar", callback_data="voltar_main")
    builder.adjust(1)
    
    await callback.message.edit_text(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")
    user_states[callback.from_user.id] = "esperando_canal"

@dp.callback_query(F.data.startswith("delcanal_"))
async def del_canal(callback: CallbackQuery):
    canal = callback.data.split("_", 1)[1]
    remove_canal(canal)
    await callback.answer(f"Canal {canal} removido!")
    await menu_canais(callback) # Atualiza a tela

# --- KEYWORDS ---
@dp.callback_query(F.data == "menu_keywords")
async def menu_keywords(callback: CallbackQuery):
    kws = get_keywords()
    
    # Se tiver muitas, limita o texto para o Telegram não recusa
    texto_kws = "\n".join([f"- {k}" for k in kws[:100]])
    if len(kws) > 100:
        texto_kws += f"\n... (e mais {len(kws)-100} palavras. Use a busca!)"
        
    texto = "🔑 **Palavras-Chave:**\n*(Se a lista estiver vazia, ele encaminha TUDO)*\n\n" 
    texto += texto_kws
    texto += "\n\nPara buscar, remover ou adicionar, use os botões abaixo ou digite no chat."
    
    builder = InlineKeyboardBuilder()
    for k in kws[:90]:
        builder.button(text=f"❌ {k}", callback_data=f"delkw_{k}")
    builder.button(text="➕ Adicionar Keyword", callback_data="add_kw_btn")
    builder.button(text="🔍 Buscar Keyword", callback_data="buscar_kw")
    builder.button(text="🔙 Voltar", callback_data="voltar_main")
    
    sizes = [2] * ((len(kws[:90]) + 1) // 2) + [1, 1, 1]
    builder.adjust(*sizes)
    
    await callback.message.edit_text(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")
    user_states[callback.from_user.id] = "esperando_kw"

@dp.callback_query(F.data == "buscar_kw")
async def btn_buscar_kw(callback: CallbackQuery):
    user_states[callback.from_user.id] = "esperando_busca_kw"
    await callback.message.edit_text("🔍 **Buscar Keyword**\n\nDigite a palavra (ou parte dela) que deseja procurar na sua lista:")
    await callback.answer()

@dp.callback_query(F.data == "add_kw_btn")
async def btn_add_kw(callback: CallbackQuery):
    user_states[callback.from_user.id] = "esperando_kw"
    await callback.message.edit_text("➕ **Adicionar Keyword**\n\nDigite a nova palavra-chave (ou várias separadas por vírgula) no chat:")
    await callback.answer()

@dp.callback_query(F.data.startswith("delkw_"))
async def del_kw(callback: CallbackQuery):
    kw = callback.data.split("_", 1)[1]
    remove_keyword(kw)
    await callback.answer(f"Keyword '{kw}' removida!")
    await menu_keywords(callback) 

# --- CONFIGURAÇÕES ---
@dp.callback_query(F.data == "menu_config")
async def menu_config(callback: CallbackQuery):
    pausado = "🔴 SIM" if get_config("pausado") == "1" else "🟢 NÃO"
    aprovacao = "🔴 SIM" if get_config("aprovacao_manual") == "1" else "🟢 NÃO"
    preco_min = get_config("preco_minimo") or "0"
    assinatura = get_config("assinatura") or "Nenhuma"

    texto = "⚙️ **Configurações Gerais**\n\n"
    texto += f"🛑 **Bot Pausado:** {pausado}\n"
    texto += f"⚖️ **Aprovação Manual:** {aprovacao}\n"
    texto += f"💲 **Preço Mínimo:** R$ {preco_min}\n"
    texto += f"📝 **Assinatura Atual:**\n`{assinatura}`"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Alternar Pausa", callback_data="toggle_pausa")
    builder.button(text="Alternar Aprovação", callback_data="toggle_aprovacao")
    builder.button(text="Alterar Preço Mínimo", callback_data="set_preco_min")
    builder.button(text="Alterar Assinatura", callback_data="set_assinatura")
    builder.button(text="🔄 Reiniciar Bot", callback_data="reboot_bot")
    builder.button(text="🔙 Voltar", callback_data="voltar_main")
    builder.adjust(1)
    
    await callback.message.edit_text(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")
    user_states[callback.from_user.id] = None

@dp.callback_query(F.data == "toggle_pausa")
async def toggle_pausa(callback: CallbackQuery):
    atual = get_config("pausado")
    novo = "0" if atual == "1" else "1"
    set_config("pausado", novo)
    await menu_config(callback)

@dp.callback_query(F.data == "toggle_aprovacao")
async def toggle_aprovacao(callback: CallbackQuery):
    atual = get_config("aprovacao_manual")
    novo = "0" if atual == "1" else "1"
    set_config("aprovacao_manual", novo)
    await menu_config(callback)

@dp.callback_query(F.data == "set_preco")
async def ask_preco(callback: CallbackQuery):
    user_states[callback.from_user.id] = "esperando_preco"
    await callback.message.answer("Digite o valor do preço mínimo (Ex: 50 ou 15.90):")
    await callback.answer()

@dp.callback_query(F.data == "set_assinatura")
async def ask_assinatura(callback: CallbackQuery):
    user_states[callback.from_user.id] = "esperando_assinatura"
    await callback.message.answer("Digite o texto da assinatura que vai no final de cada postagem (suporta HTML/Links):\nEnvie 'LIMPAR' para remover a assinatura.")
    await callback.answer()

# --- VOLTAR ---
@dp.callback_query(F.data == "reboot_bot")
async def handle_reboot_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Sem permissão.")
        return
    await callback.message.answer("🔄 **Comando de reinicialização recebido.**\nO sistema irá reiniciar o processo agora.")
    await asyncio.sleep(1)
    
    # Fecha conexões de forma segura
    try:
        from publisher import bot
        await bot.session.close()
    except: pass
    try:
        from monitor import client as userbot
        await userbot.disconnect()
    except: pass
    
    os.execv(sys.executable, ['python'] + sys.argv)

@dp.callback_query(F.data == "voltar_main")
async def voltar_main(callback: CallbackQuery):
    user_states[callback.from_user.id] = None
    await callback.message.edit_text(
        "🛠️ **Painel de Controle - Literalmente Promo**\n\nEscolha uma opção:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# --- ADMIN MANAGEMENT ---
@dp.callback_query(F.data == "menu_admins")
async def menu_admins(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Acesso negado.", show_alert=True)
        return
    
    admins = get_admins()
    texto = "👥 **Administradores do Bot:**\n\n"
    for uid, uname in admins:
        texto += f"- `{uid}` ({uname or 'S/N'})\n"
    texto += "\nPara remover um admin, clique abaixo. Para adicionar, envie o ID do usuário no chat."
    
    builder = InlineKeyboardBuilder()
    for uid, uname in admins:
        builder.button(text=f"❌ {uid}", callback_data=f"deladmin_{uid}")
    builder.button(text="🔙 Voltar", callback_data="voltar_main")
    builder.adjust(1)
    
    await callback.message.edit_text(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")
    user_states[callback.from_user.id] = "esperando_admin_id"

@dp.callback_query(F.data.startswith("deladmin_"))
async def del_admin_handler(callback: CallbackQuery):
    uid = int(callback.data.split("_")[1])
    if uid == callback.from_user.id:
        await callback.answer("Você não pode remover a si mesmo!", show_alert=True)
        return
    remove_admin(uid)
    await callback.answer("Admin removido!")
    await menu_admins(callback)

# --- SORTEIOS MANAGEMENT ---
@dp.callback_query(F.data == "menu_sorteios")
async def menu_sorteios(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Acesso negado.", show_alert=True)
        return
    
    sorteios = get_active_sorteios()
    texto = "🎁 **Sorteios Ativos:**\n\n"
    if not sorteios:
        texto += "Nenhum sorteio ativo no momento."
    else:
        for sid, premio, data in sorteios:
            texto += f"- #{sid}: {premio} (Criado em: {data})\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Criar Novo Sorteio", callback_data="sorteio_novo")
    for sid, premio, data in sorteios:
        builder.button(text=f"🎲 Rodar #{sid}", callback_data=f"sorteio_rodar_{sid}")
    builder.button(text="🔙 Voltar", callback_data="voltar_main")
    builder.adjust(1)
    
    await callback.message.edit_text(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "sorteio_novo")
async def sorteio_novo(callback: CallbackQuery):
    user_states[callback.from_user.id] = "esperando_premio_sorteio"
    await callback.message.answer("Digite o nome do prêmio para o novo sorteio:")
    await callback.answer()

@dp.callback_query(F.data.startswith("sorteio_rodar_"))
async def sorteio_rodar(callback: CallbackQuery):
    sid = int(callback.data.split("_")[-1])
    await callback.answer("Iniciando sorteio... Aguarde.")
    
    from monitor import client as telethon_client
    from config import TARGET_CHANNEL
    import random
    
    try:
        admins_ids = [a[0] for a in get_admins()]
        
        membros = []
        async for user in telethon_client.iter_participants(TARGET_CHANNEL):
            if not user.bot and user.id not in admins_ids:
                membros.append(user)
        
        if not membros:
            await callback.message.answer("❌ Não foram encontrados membros elegíveis para o sorteio.")
            return
            
        ganhador = random.choice(membros)
        nome_ganhador = (ganhador.first_name or "") + (" " + ganhador.last_name if ganhador.last_name else "")
        if not nome_ganhador: nome_ganhador = f"ID: {ganhador.id}"
        
        finalize_sorteio(sid, ganhador.id, nome_ganhador)
        
        await callback.message.answer(
            f"🎉 **SORTEIO REALIZADO!** 🎉\n\n"
            f"O vencedor foi: **{nome_ganhador}**\n"
            f"ID: `{ganhador.id}`\n"
            f"Username: @{ganhador.username if ganhador.username else 'N/A'}"
        )
        
        from publisher import bot as aiogram_bot
        await aiogram_bot.send_message(TARGET_CHANNEL, f"🎉 Parabéns {nome_ganhador}, você ganhou o sorteio! Entre em contato com a administração.")
        
    except Exception as e:
        await callback.message.answer(f"❌ Erro ao rodar sorteio: {e}")

# --- TRATAR MENSAGENS DIGITADAS ---
@dp.message()
async def handle_text(message: Message):
    try:
        user_id = message.from_user.id
        
        # Restrição de Admin
        if not is_admin(user_id):
            return
        
        # Salva o primeiro admin se a lista for vazia
        if not get_admins():
            add_admin(user_id, message.from_user.username)

        estado = user_states.get(user_id)
        
        if estado is None:
            # Tenta detectar se o usuário mandou um link direto da Amazon ou ML
            texto = message.text.lower() if message.text else ""
            if any(domain in texto for domain in ["amazon.com.br", "amzlink.to", "amzn.to", "mercadolivre.com", "mlb.sh"]):
                print(f"🔗 Link auto-detectado do admin: {message.text}")
                await start_criar_oferta_msg(message)
                estado = user_states.get(user_id)
    except Exception as e:
        print(f"❌ Erro no início do handle_text: {e}")
        return

    if estado == "esperando_canal":
        canal = message.text.strip().replace("@", "")
        if add_canal(canal):
            await message.answer(f"✅ Canal `{canal}` adicionado à lista de monitoramento!")
        else:
            await message.answer("⚠️ Este canal já está sendo monitorado.")
        user_states[message.from_user.id] = None
            
    elif estado == "esperando_edicao_texto":
        item_id = user_temp_data.get(message.from_user.id, {}).get("edit_item_id")
        from monitor import ofertas_pendentes_admin
        
        if item_id is not None and 0 <= item_id < len(ofertas_pendentes_admin):
            ofertas_pendentes_admin[item_id]["texto"] = message.text
            user_states[message.from_user.id] = None
            await message.answer("✅ Texto atualizado! Gerando nova prévia...")
            
            oferta = ofertas_pendentes_admin[item_id]
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Postar", callback_data=f"aprovar_{item_id}"),
                    InlineKeyboardButton(text="✏️ Editar", callback_data=f"editar_{item_id}"),
                    InlineKeyboardButton(text="❌ Descartar", callback_data=f"recusar_{item_id}")
                ]
            ])
            msg_amostra = f"**PRÉVIA ATUALIZADA:**\n\n{message.text}"
            
            from aiogram.types import FSInputFile
            if oferta["media"]:
                photo = FSInputFile(oferta["media"])
                await message.answer_photo(photo=photo, caption=msg_amostra, reply_markup=markup, parse_mode="HTML")
            else:
                await message.answer(text=msg_amostra, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await message.answer("❌ Erro ao localizar a oferta para edição.")
            user_states[message.from_user.id] = None

    elif estado == "esperando_kw":
        kws = [k.strip() for k in message.text.lower().split(",") if k.strip()]
        adicionadas = []
        ja_existem = []
        for kw in kws:
            if add_keyword(kw):
                adicionadas.append(kw)
            else:
                ja_existem.append(kw)
        
        msg_parts = []
        if adicionadas:
            msg_parts.append(f"✅ Keyword(s) adicionada(s): `{', '.join(adicionadas)}`")
        if ja_existem:
            msg_parts.append(f"⚠️ Já cadastrada(s): `{', '.join(ja_existem)}`")
            
        if not msg_parts:
            msg_parts.append("⚠️ Nenhuma keyword válida informada.")
            
        await message.answer("\n".join(msg_parts))
        user_states[message.from_user.id] = None

    elif estado == "esperando_busca_kw":
        busca = message.text.strip().lower()
        kws = get_keywords()
        resultados = [k for k in kws if busca in k.lower()]
        
        if resultados:
            texto = f"🔍 **Resultados para:** `{busca}`\n\n" + "\n".join([f"- {k}" for k in resultados[:100]])
            texto += "\n\nPara remover, clique abaixo. Para adicionar novas, digite no chat."
        else:
            texto = f"🔍 **Nenhum resultado para:** `{busca}`\n\nPara adicionar como nova keyword, basta digitar ela no chat."
            
        builder = InlineKeyboardBuilder()
        for k in resultados[:90]:
            builder.button(text=f"❌ {k}", callback_data=f"delkw_{k}")
        builder.button(text="🔍 Nova Busca", callback_data="buscar_kw")
        builder.button(text="🔙 Voltar p/ Keywords", callback_data="menu_keywords")
        
        sizes = [2] * ((len(resultados[:90]) + 1) // 2) + [1, 1]
        builder.adjust(*sizes)
        
        await message.answer(texto, reply_markup=builder.as_markup(), parse_mode="Markdown")
        user_states[message.from_user.id] = "esperando_kw"

    elif estado == "esperando_preco":
        try:
            val = float(message.text.replace(',','.'))
            set_config("preco_minimo", str(val))
            await message.answer(f"✅ Preço mínimo configurado para R$ {val:.2f}")
        except:
            await message.answer("❌ Valor inválido.")
        user_states[message.from_user.id] = None

    elif estado == "esperando_assinatura":
        if message.text.strip().upper() == "LIMPAR":
            set_config("assinatura", "")
            await message.answer("✅ Assinatura removida.")
        else:
            set_config("assinatura", message.text)
            await message.answer("✅ Nova assinatura configurada!")
        user_states[message.from_user.id] = None

    elif estado == "esperando_link_criacao":
        link = message.text.strip()
        user_temp_data[message.from_user.id] = {"link": link}
        msg_status = await message.answer("🔍 Extraindo informações da página...")
        
        try:
            from scraper import fetch_product_metadata
            metadata = await fetch_product_metadata(link)
            user_temp_data[message.from_user.id]["titulo"] = metadata.get("title", "")
            user_temp_data[message.from_user.id]["local_image_path"] = metadata.get("local_image_path", "")
            
            status = metadata.get("status_code", 200)
            titulo_achado = metadata.get('title')
            
            if status in [403, 503, 404] or not titulo_achado:
                user_states[message.from_user.id] = "esperando_titulo_criacao"
                warn_msg = "⚠️ Bloqueio detectado ou falha na extração.\nAmazon, ML ou KaBuM bloquearam o acesso.\n\n"
                retry_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Tentar Novamente", callback_data="retry_scraping")]
                ])
                await message.answer(f"{warn_msg}Digite o nome do livro manualmente para continuar:", reply_markup=retry_kb)
            else:
                user_states[message.from_user.id] = "esperando_preco_criacao"
                await message.answer(f"✅ Identifiquei: **{titulo_achado}**\n\nQual é o valor final? (Só números):")
        finally:
            try:
                await msg_status.delete()
            except: pass

    elif estado == "esperando_titulo_criacao":
        user_temp_data[message.from_user.id]["titulo"] = message.text.strip()
        user_states[message.from_user.id] = "esperando_preco_criacao"
        await message.answer(f"✅ Título definido.\n\nQual é o valor final? (Só números):")

    elif estado == "esperando_preco_criacao":
        user_temp_data[message.from_user.id]["preco"] = message.text.strip()
        user_states[message.from_user.id] = "esperando_cupom_criacao"
        skip_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Pular", callback_data="skip_coupon")]
        ])
        await message.answer("💸 E o Cupom? (Digite ou clique em Pular):", reply_markup=skip_kb)

    elif estado == "esperando_cupom_criacao":
        user_temp_data[message.from_user.id]["cupom"] = message.text.strip()
        user_states[message.from_user.id] = "esperando_observacao_criacao"
        skip_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Pular", callback_data="skip_obs")]
        ])
        await message.answer("💡 Alguma observação ou destaque? (Ex: Frete Grátis, Prime Only, etc. Ou clique em Pular):", reply_markup=skip_kb)

    elif estado == "esperando_observacao_criacao":
        user_temp_data[message.from_user.id]["observacao"] = message.text.strip()
        choice_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Pela Inteligência Artificial", callback_data="text_mode_ai"),
                InlineKeyboardButton(text="✍️ Escrever Manualmente", callback_data="text_mode_manual")
            ]
        ])
        user_states[message.from_user.id] = "esperando_modo_texto"
        await message.answer("📝 Como deseja gerar o texto?", reply_markup=choice_kb)

    elif estado == "esperando_texto_manual":
        user_temp_data[message.from_user.id]["texto_manual"] = message.text
        user_states[message.from_user.id] = None
        await finalizar_criacao_manual(message, message.from_user.id)

    elif estado == "esperando_modo_texto":
        await message.answer("⚠️ Escolha uma das opções nos botões.")
        
    elif estado == "esperando_admin_id":
        try:
            new_uid = int(message.text.strip())
            if add_admin(new_uid):
                await message.answer(f"✅ Usuário `{new_uid}` adicionado!")
            else:
                await message.answer("⚠️ Este usuário já é Admin.")
        except:
            await message.answer("❌ ID inválido.")
        user_states[message.from_user.id] = None
        
    elif estado == "esperando_premio_sorteio":
        premio = message.text.strip()
        create_sorteio(premio)
        await message.answer(f"✅ Sorteio de '{premio}' criado!")
        user_states[message.from_user.id] = None
        
async def finalizar_criacao_manual(event_message: Message, user_id: int, modo_ai: bool = False):
    data = user_temp_data.get(user_id)
    if not data:
        await event_message.answer("❌ Erro: Dados perdidos.")
        return

    msg = await event_message.answer("✨ Processando oferta...")
    from rewriter import gerar_promocao_por_link
    from links import process_and_replace_links
    from monitor import post_queue
    from watermark import apply_watermark
    
    try:
        if modo_ai:
            texto_base = await gerar_promocao_por_link(
                data.get("titulo", "Livro"), 
                data.get("link", ""), 
                data.get("preco", "0.00"), 
                data.get("cupom", ""),
                data.get("observacao", "")
            )
        else:
            texto_base = data.get("texto_manual", "Oferta sem descrição.")

        # Garantir marcador de link
        if "[LINK_" not in texto_base:
            texto_base += "\n\n[LINK_0]"

        texto_com_placeholders, placeholder_map = await process_and_replace_links(texto_base, data.get('link'))
        clean_text = texto_com_placeholders
        if placeholder_map:
            for placeholder, final_url in placeholder_map.items():
                if final_url:
                    botao_html = f"🛒 <a href='{final_url}'>Pegar promoção</a>"
                    clean_text = clean_text.replace(placeholder, botao_html)
        
        clean_text = re.sub(r'\[LINK_\d+\]', '', clean_text)
        assinatura = get_config("assinatura")
        if assinatura: clean_text += f"\n\n{assinatura}"
            
        img_path = data.get("local_image_path")
        if img_path: img_path = apply_watermark(img_path)
            
        await post_queue.put((clean_text, img_path, None))
        await msg.delete()
        await event_message.answer("✅ **Oferta Criada com Sucesso!**")
    except Exception as e:
        await event_message.answer(f"❌ Erro: {e}")

@dp.callback_query(F.data == "skip_coupon")
async def handle_skip_coupon(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_temp_data[user_id]["cupom"] = "-"
    user_states[user_id] = "esperando_observacao_criacao"
    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Pular", callback_data="skip_obs")]
    ])
    await callback.message.edit_text("💡 Alguma observação ou destaque? (Ex: Frete Grátis, Prime Only, etc. Ou clique em Pular):", reply_markup=skip_kb)
    await callback.answer()

@dp.callback_query(F.data == "skip_obs")
async def handle_skip_obs(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_temp_data[user_id]["observacao"] = ""
    choice_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Pela Inteligência Artificial", callback_data="text_mode_ai"),
            InlineKeyboardButton(text="✍️ Escrever Manualmente", callback_data="text_mode_manual")
        ]
    ])
    user_states[user_id] = "esperando_modo_texto"
    await callback.message.edit_text("📝 Como deseja gerar o texto?", reply_markup=choice_kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("text_mode_"))
async def handle_text_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.split("_")[-1]
    if mode == "ai":
        await callback.message.edit_text("✨ Gerando texto com IA...")
        await finalizar_criacao_manual(callback.message, user_id, modo_ai=True)
    else:
        user_states[user_id] = "esperando_texto_manual"
        await callback.message.edit_text("✍️ Digite agora o texto da promoção:")
    await callback.answer()

@dp.callback_query(F.data.startswith("aprovar_") | F.data.startswith("recusar_") | F.data.startswith("editar_"))
async def tratar_aprovacao_manual(callback: CallbackQuery):
    from monitor import post_queue, ofertas_pendentes_admin
    parts = callback.data.split("_")
    acao = parts[0]
    item_id = int(parts[1])
    
    if item_id < 0 or item_id >= len(ofertas_pendentes_admin):
        await callback.answer("⚠️ Oferta não encontrada.")
        return
        
    oferta = ofertas_pendentes_admin[item_id]
    if not oferta:
        await callback.answer("⚠️ Já processada.")
        return

    if acao == "editar":
        user_id = callback.from_user.id
        user_states[user_id] = "esperando_edicao_texto"
        user_temp_data[user_id] = {"edit_item_id": item_id}
        await callback.message.answer("✍️ Envie o novo texto completo:")
        await callback.answer()
    elif acao == "aprovar":
        await callback.answer("✅ Aprovada!")
        await post_queue.put((oferta["texto"], oferta["media"], None))
        await callback.message.edit_caption(caption="✅ **APROVADA**", reply_markup=None)
        ofertas_pendentes_admin[item_id] = None
    else:
        await callback.answer("❌ Recusada!")
        await callback.message.edit_caption(caption="❌ **RECUSADA**", reply_markup=None)
        if oferta["media"] and os.path.exists(oferta["media"]):
            try: os.remove(oferta["media"])
            except: pass
        ofertas_pendentes_admin[item_id] = None

from aiogram.types.error_event import ErrorEvent
import traceback

@dp.error()
async def global_error_handler(event: ErrorEvent):
    """Captura erros globais do Aiogram e notifica o admin"""
    print(f"⚠️ Erro Global Capturado: {event.exception}")
    try:
        admin_id_str = get_config("admin_id")
        if admin_id_str:
            error_msg = f"⚠️ **ALERTA DE SISTEMA: ERRO INTERNO** ⚠️\n\n**Tipo:** `{type(event.exception).__name__}`\n**Erro:** `{str(event.exception)[:500]}`\n\n*Detalhes no log do servidor.*"
            await bot.send_message(chat_id=int(admin_id_str), text=error_msg, parse_mode="Markdown")
    except Exception as notify_err:
        print(f"Não foi possível notificar o admin sobre o erro: {notify_err}")

async def start_admin_bot():
    print("🤖 Painel Admin do Bot iniciado (Aguardando /admin no Telegram)")
    await bot.set_my_commands([
        BotCommand(command="start", description="Painel Admin"),
        BotCommand(command="enviar", description="Enviar Promoção via Link"),
    ])
    
    # Enviar notificação de reinício
    try:
        admin_id_str = get_config("admin_id")
        if admin_id_str:
            await bot.send_message(
                chat_id=int(admin_id_str), 
                text="🚀 **SISTEMA INICIADO / REINICIADO**\n\n✅ Bot ativo e monitorando grupos selecionados.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"Aviso: Não foi possível enviar notificação de startup: {e}")
        
    await dp.start_polling(bot)
