import httpx
from bs4 import BeautifulSoup
import os
import re
import asyncio
import random
import json
from typing import Dict, List, Any, Optional

def clean_amazon_url(url: str) -> str:
    """Limpa parâmetros de rastreio da Amazon para evitar bloqueios e URLs gigantes."""
    if "amazon.com.br" not in url:
        return url
    
    # Busca o padrão /dp/ASIN ou /gp/product/ASIN
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    if match:
        asin = match.group(1)
        return f"https://www.amazon.com.br/dp/{asin}"
    return url

def get_header_profiles() -> List[Dict[str, str]]:
    """Retorna uma lista de perfis de headers realistas."""
    return [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com.br/",
        },
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    ]

async def fetch_product_metadata(url: str) -> dict:
    """
    Acessa a URL e tenta extrair o título do produto e a imagem principal.
    Implementa Smart Scraper com rotação de headers e auto-retry.
    """
    url = clean_amazon_url(url)
    print(f"🔍 [SmartScraper] Iniciando extração: {url}")

    profiles = get_header_profiles()
    max_retries = 3
    
    metadata = {
        "title": "",
        "image_url": "",
        "local_image_path": "",
        "status_code": 200
    }

    for attempt in range(max_retries):
        headers = random.choice(profiles)
        ua = headers.get("User-Agent", "")
        print(f"🔄 Tentativa {attempt + 1}/{max_retries} usando perfil: {ua[:50]}...")
        
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                metadata["status_code"] = response.status_code
                
                if response.status_code != 200:
                    print(f"⚠️ Status {response.status_code} na tentativa {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                title_tag = soup.find("title")
                raw_title = title_tag.text.strip() if title_tag else ""
                
                # Detecta bloqueio pelo conteúdo do título
                is_blocked = any(kw in raw_title.lower() for kw in ["robot check", "captcha", "503 - erro", "service unavailable", "indisponível"])
                
                if is_blocked:
                    print(f"🚫 Bloqueio detectado no título: '{raw_title}'")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(1.5, 4.0))
                        continue
                    else:
                        # Se for a última tentativa e ainda estiver bloqueado, não define o título
                        metadata["title"] = ""
                        break
                
                # Se chegou aqui, parece que temos um HTML válido
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content") and not any(kw in str(og_title.get("content")).lower() for kw in ["captcha", "robot"]):
                    metadata["title"] = og_title["content"]
                elif raw_title:
                    metadata["title"] = raw_title.split(" | Amazon.com.br")[0].split(": Amazon.com.br:")[0]

                # Se o título extraído ainda parecer erro, limpa
                extracted_title = str(metadata.get("title", ""))
                if any(kw in extracted_title.lower() for kw in ["503 - erro", "service unavailable", "robot check"]):
                    metadata["title"] = ""
                    if attempt < max_retries - 1:
                        continue
                    else:
                        break

                # Tenta pegar og:image
                og_image = soup.find("meta", property="og:image")
                if og_image and og_image.get("content"):
                    metadata["image_url"] = str(og_image["content"])
                
                # Fallbacks Amazon para imagem
                current_img = str(metadata.get("image_url", ""))
                if not current_img or "captcha" in current_img.lower():
                    img_tag = soup.find("img", id="landingImage") or soup.find("img", id="main-image")
                    if img_tag:
                        # data-a-dynamic-image
                        dyn_data = img_tag.get("data-a-dynamic-image")
                        if dyn_data:
                            try:
                                dyn_img = json.loads(str(dyn_data))
                                metadata["image_url"] = str(list(dyn_img.keys())[0]) if dyn_img else ""
                            except: pass
                        
                        if not metadata.get("image_url"):
                            metadata["image_url"] = str(img_tag.get("data-old-hires") or img_tag.get("src") or "")

                # Se temos título e imagem (ou pelo menos título), sucesso!
                final_title = str(metadata.get("title", ""))
                if final_title and not is_blocked:
                    print(f"✅ Sucesso na tentativa {attempt + 1}!")
                    
                    # Tenta baixar a imagem
                    if metadata["image_url"]:
                        img_url = str(metadata["image_url"])
                        if img_url.startswith("//"): img_url = "https:" + img_url
                        
                        try:
                            img_res = await client.get(img_url, headers=headers, timeout=10.0)
                            if img_res.status_code == 200:
                                if not os.path.exists("downloads"): os.makedirs("downloads")
                                file_name = f"downloads/scraped_{random.randint(1000, 9999)}.jpg"
                                with open(file_name, "wb") as f:
                                    f.write(img_res.content)
                                metadata["local_image_path"] = file_name
                                print(f"📸 Imagem salva: {file_name}")
                        except Exception as e:
                            print(f"❌ Erro ao baixar imagem: {e}")
                            
                    return metadata
                    
        except Exception as e:
            print(f"❌ Erro na tentativa {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
    
    return metadata

def extract_price(text: str) -> str | None:
    """Extrai o valor numérico de um texto (ex: R$ 1.200,50 -> 1200.50)."""
    if not text:
        return None
    match = re.search(r'(?:R\$\s?)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', text)
    if match:
        return match.group(1).replace('.', '').replace(',', '.')
    return None
