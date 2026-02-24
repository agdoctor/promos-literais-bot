import requests
import json
import os
from config import GREEN_API_INSTANCE_ID, GREEN_API_TOKEN, WHATSAPP_DESTINATION, WHATSAPP_ENABLED

def send_whatsapp_msg(text: str, media_path: str | None = None):
    """
    Envia uma mensagem para o WhatsApp via Green-API.
    Suporta texto e imagem (via Upload).
    """
    if not WHATSAPP_ENABLED or not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not WHATSAPP_DESTINATION:
        return None

    try:
        # Se houver mídia local, fazemos o upload
        if media_path and os.path.exists(media_path):
            url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendFileByUpload/{GREEN_API_TOKEN}"
            
            payload = {
                'chatId': WHATSAPP_DESTINATION,
                'caption': text
            }
            
            files = [
                ('file', (os.path.basename(media_path), open(media_path, 'rb'), 'image/jpeg'))
            ]
            
            response = requests.post(url, data=payload, files=files, timeout=30)
        else:
            # Caso contrário, apenas texto
            url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
            payload = {
                "chatId": WHATSAPP_DESTINATION,
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
