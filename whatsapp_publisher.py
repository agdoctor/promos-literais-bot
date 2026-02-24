import requests
import json
import os
from config import GREEN_API_INSTANCE_ID, GREEN_API_TOKEN, WHATSAPP_DESTINATION, WHATSAPP_ENABLED, GREEN_API_HOST

def send_whatsapp_msg(text: str, media_path: str | None = None):
    """
    Envia uma mensagem para o WhatsApp via Green-API.
    Suporta texto e imagem (via Upload).
    """
    try:
        from database import get_config
    except ImportError:
        # Fallback caso database não exista no contexto (improvável, mas seguro)
        def get_config(x): return ""
    
    # Busca configurações e limpa espaços (Prioridade: Banco de dados > Config.py/Env)
    db_enabled = get_config("whatsapp_enabled").lower() == "true"
    enabled = db_enabled or WHATSAPP_ENABLED
    
    instance_id = (get_config("green_api_instance_id") or GREEN_API_INSTANCE_ID or "").strip()
    token = (get_config("green_api_token") or GREEN_API_TOKEN or "").strip()
    host = (get_config("green_api_host") or GREEN_API_HOST or "api.green-api.com").strip()
    destination = (get_config("whatsapp_destination") or WHATSAPP_DESTINATION or "").strip()

    if not enabled:
        print("⚠️ WhatsApp desabilitado nas configurações.")
        return None

    if not instance_id or not token or not destination:
        print(f"⚠️ Faltam credenciais: ID={instance_id}, Destino='{destination}'")
        return None

    # Limpar o host: remove protocolos, barras e corrige falta de hífen em 'greenapi'
    host_clean = host.replace("https://", "").replace("http://", "").strip("/")
    if "greenapi.com" in host_clean and "green-api.com" not in host_clean:
        host_clean = host_clean.replace("greenapi.com", "green-api.com")
    
    print(f"📡 Tentando enviar para WhatsApp: Host={host_clean}, Instance={instance_id}, Destino={destination}")

    try:
        # Se houver mídia local, fazemos o upload
        if media_path and os.path.exists(media_path):
            url = f"https://{host_clean}/waInstance{instance_id}/sendFileByUpload/{token}"
            
            payload = {
                'chatId': destination,
                'caption': text
            }
            
            files = [
                ('file', (os.path.basename(media_path), open(media_path, 'rb'), 'image/jpeg'))
            ]
            
            response = requests.post(url, data=payload, files=files, timeout=30)
        else:
            # Caso contrário, apenas texto
            url = f"https://{host_clean}/waInstance{instance_id}/sendMessage/{token}"
            payload = {
                "chatId": destination,
                "message": text
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
        
        if response.status_code == 200:
            print("✅ Mensagem enviada para o WhatsApp com sucesso!")
            return response.json()
        else:
            print(f"❌ Erro Green-API ({response.status_code}): {response.text}")
            return None

    except Exception as e:
        print(f"❌ Erro ao enviar para WhatsApp: {e}")
        return None
