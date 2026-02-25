import requests
import json
import os
from config import GREEN_API_INSTANCE_ID, GREEN_API_TOKEN, WHATSAPP_DESTINATION, WHATSAPP_ENABLED, GREEN_API_HOST

def format_whatsapp_text(html_text: str) -> str:
    """
    Converte HTML básico (do Telegram) para o formato do WhatsApp.
    Handles <b>, <i>, <u>, <code> e <a href="...">.
    """
    import re
    import html
    
    # Negrito
    text = html_text.replace("<b>", "*").replace("</b>", "*")
    text = text.replace("<strong>", "*").replace("</strong>", "*")
    # Itálico
    text = text.replace("<i>", "_").replace("</i>", "_")
    text = text.replace("<em>", "_").replace("</em>", "_")
    # Sublinhado (WhatsApp não tem, removemos a tag)
    text = text.replace("<u>", "").replace("</u>", "")
    # Monospace
    text = text.replace("<code>", "```").replace("</code>", "```")
    text = text.replace("<pre>", "```").replace("</pre>", "```")

    # Links: <a href="url">label</a> -> Formato "Botão Visual" para WhatsApp
    def link_repl(match):
        url = match.group(1).strip()
        label = match.group(2).strip()
        generics = ["pegar promoção", "clique aqui", "comprar", "link", "aproveite", "ir para a loja", "oferta", "ver mais", "pegar", "quero", "eu quero", "resgatar"]
        
        # Se for um link genérico/CTA, formatamos como "Botão Visual" destacado com emojis
        if label.lower() in generics or not label:
            return f"\n\n*🛍️ PEGAR PROMOÇÃO:*\n{url}"
        
        # Se for um link informativo (ex: Cupom ou Canal), mantemos mais discreto/inline
        if len(label) < 15 or "t.me/" in url.lower():
            return f" *{label.upper()}*: {url} "
            
        # Para outros links (ex: títulos), usamos um formato de destaque simples
        return f"\n\n*👉 {label.upper()}:*\n{url}"

    # Regex robusta para links (suporta aspas simples e duplas)
    text = re.sub(r'<a\s+.*?href=["\'](.*?)["\'].*?>(.*?)</a>', link_repl, text, flags=re.DOTALL | re.IGNORECASE)
    
    # Limpa qualquer tag restante
    text = re.sub(r'<.*?>', '', text)
    
    # Converte entidades HTML (&nbsp;, &lt;, etc)
    text = html.unescape(text)
    
    return text.strip()

def send_whatsapp_msg(text: str, media_path: str | None = None):
    """
    Envia uma mensagem para o WhatsApp via Green-API.
    Suporta texto e imagem (via Upload).
    """
    from database import get_config
    
    # Busca configurações e limpa espaços (Prioridade: Banco de dados > Config.py/Env)
    db_enabled = get_config("whatsapp_enabled").lower() == "true"
    enabled = db_enabled or WHATSAPP_ENABLED
    
    instance_id = (get_config("green_api_instance_id") or GREEN_API_INSTANCE_ID or "").strip()
    # Garante que o instance_id tenha apenas os números
    instance_id_clean = instance_id.replace("waInstance", "")
    token = (get_config("green_api_token") or GREEN_API_TOKEN or "").strip()
    host = (get_config("green_api_host") or GREEN_API_HOST or "api.green-api.com").strip()
    destination = (get_config("whatsapp_destination") or WHATSAPP_DESTINATION or "").strip()

    if not enabled:
        print("⚠️ WhatsApp desabilitado nas configurações.")
        return None

    if not instance_id_clean or not token or not destination:
        print(f"⚠️ Faltam credenciais: ID={instance_id_clean}, Destino='{destination}'")
        return None

    # Limpar o host: remove protocolos, barras e corrige falta de hífen em 'greenapi'
    host_clean = host.replace("https://", "").replace("http://", "").strip("/")
    if "greenapi.com" in host_clean and "green-api.com" not in host_clean:
        host_clean = host_clean.replace("greenapi.com", "green-api.com")
    
    destinations = [d.strip() for d in destination.split(",") if d.strip()]
    if not destinations:
        print("⚠️ Nenhuma conta de destino válida encontrada.")
        return None

    import time
    responses = []
    common_headers = {'Accept': 'application/json'}
    
    for idx, dest in enumerate(destinations):
        if idx > 0:
            print(f"⏳ Aguardando 1.5s antes de enviar para o próximo grupo ({idx+1}/{len(destinations)})...")
            time.sleep(1.5)
            
        print(f"📡 Tentando enviar para WhatsApp ({dest}): Host={host_clean}, Instance={instance_id_clean}")

        try:
            # Se houver mídia local, fazemos o upload
            if media_path and os.path.exists(media_path):
                url = f"https://{host_clean}/waInstance{instance_id_clean}/sendFileByUpload/{token}"
                
                payload = {
                    'chatId': dest,
                    'caption': text
                }
                
                files = [
                    ('file', (os.path.basename(media_path), open(media_path, 'rb'), 'image/jpeg'))
                ]
                
                response = requests.post(url, data=payload, files=files, headers=common_headers, timeout=30)
            else:
                # Caso contrário, apenas texto
                url = f"https://{host_clean}/waInstance{instance_id_clean}/sendMessage/{token}"
                payload = {
                    "chatId": dest,
                    "message": text
                }
                headers = {**common_headers, 'Content-Type': 'application/json'}
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
            
            if response.status_code == 200:
                print(f"✅ Mensagem enviada para {dest} com sucesso!")
                responses.append(response.json())
            else:
                print(f"❌ Erro Green-API para {dest} ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"❌ Erro ao enviar para {dest}: {e}")

    return responses if responses else None

def get_whatsapp_group_info(invite_link: str):
    """
    Tenta obter informações de um grupo (incluindo o ID) a partir do link de convite.
    Usa o método da Green-API: getGroupDataFromInviteLink
    """
    from database import get_config
    
    instance_id = (get_config("green_api_instance_id") or GREEN_API_INSTANCE_ID or "").strip()
    # Garante que o instance_id tenha apenas os números
    instance_id_clean = "".join(filter(str.isdigit, instance_id))
    token = (get_config("green_api_token") or GREEN_API_TOKEN or "").strip()
    host = (get_config("green_api_host") or GREEN_API_HOST or "api.green-api.com").strip()

    if not instance_id_clean or not token:
        return {"error": "Faltam credenciais da Green-API (Instance ID ou Token)."}

    # Limpar o host
    host_clean = host.replace("https://", "").replace("http://", "").strip("/")
    if "greenapi.com" in host_clean and "green-api.com" not in host_clean:
        host_clean = host_clean.replace("greenapi.com", "green-api.com")
        
    url = f"https://{host_clean}/waInstance{instance_id_clean}/getGroupDataFromInviteLink/{token}"
    payload = {"inviteLink": invite_link}
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            return {"error": "Erro Green-API (403): O link pode ser inválido ou o método não é suportado pelo seu plano ( Tariff DEVELOPER)."}
        else:
            return {"error": f"Erro Green-API ({response.status_code}): {response.text}"}
    except Exception as e:
        return {"error": f"Erro de conexão: {str(e)}"}

def list_whatsapp_groups():
    """Retorna uma lista de grupos que a conta Green-API participa."""
    from database import get_config
    
    instance_id = (get_config("green_api_instance_id") or GREEN_API_INSTANCE_ID or "").strip()
    instance_id_clean = "".join(filter(str.isdigit, instance_id))
    token = (get_config("green_api_token") or GREEN_API_TOKEN or "").strip()
    host = (get_config("green_api_host") or GREEN_API_HOST or "api.green-api.com").strip()

    if not instance_id_clean or not token:
        return {"error": "Faltam credenciais da Green-API."}

    host_clean = host.replace("https://", "").replace("http://", "").strip("/")
    url = f"https://{host_clean}/waInstance{instance_id_clean}/getGroups/{token}"
    
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            groups = response.json()
            # Filtra apenas grupos onde o usuário é administrador
            # A Green-API retorna isAdmin: True/False no método getGroups
            admin_groups = [g for g in groups if g.get("isAdmin") is True]
            return {"groups": admin_groups}
        else:
            return {"error": f"Erro Green-API ({response.status_code}): {response.text}"}
    except Exception as e:
        return {"error": f"Erro de conexão: {str(e)}"}
