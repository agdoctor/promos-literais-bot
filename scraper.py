from curl_cffi import requests
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

def get_random_browser() -> str:
    """Retorna um perfil de navegador aleatório suportado pelo curl_cffi."""
    return random.choice(["chrome110", "chrome116", "chrome120", "safari15_5"])

async def fetch_product_metadata(url: str) -> dict:
    """
    Acessa a URL e tenta extrair o título do produto e a imagem principal usando curl_cffi
    para personificação de TLS de navegadores reais (bypass robusto).
    """
    url = clean_amazon_url(url)
    print(f"🔍 [SmartScraper TLS] Iniciando extração: {url}")

    max_retries = 3
    metadata = {
        "title": "",
        "image_url": "",
        "local_image_path": "",
        "status_code": 200
    }

    for attempt in range(max_retries):
        browser = get_random_browser()
        print(f"🔄 Tentativa {attempt + 1}/{max_retries} usando personificação: {browser}")
        
        try:
            from curl_cffi.requests import AsyncSession
            
            async with AsyncSession(impersonate=browser) as s:
                response = await s.get(url, timeout=20, allow_redirects=True)
                metadata["status_code"] = response.status_code
                
                if response.status_code != 200:
                    print(f"⚠️ Status {response.status_code} na tentativa {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                title_tag = soup.find("title")
                raw_title = title_tag.text.strip() if title_tag else ""
                
                # Detecta bloqueio real (página de erro ou título idêntico ao site)
                low_title = raw_title.lower().strip()
                is_blocked = False
                
                # Keywords que indicam bloqueio REAL
                block_keywords = ["robot check", "captcha", "503 - erro", "service unavailable", "indisponível", "acesso negado", "forbidden"]
                if any(kw in low_title for kw in block_keywords):
                    is_blocked = True
                
                # Se o título for APENAS o nome da loja ou curto demais + nome da loja
                if not is_blocked:
                    generic_names = ["amazon.com.br", "mercado livre", "mercadolivre", "amazon"]
                    if low_title in generic_names or (len(low_title) < 20 and any(kw == low_title for kw in generic_names)):
                        is_blocked = True

                if is_blocked:
                    print(f"🚫 Bloqueio real detectado no título: '{raw_title}'")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        continue
                    else:
                        metadata["title"] = ""
                        break
                
                # Sucesso parcial: Tentar extrair dados
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content") and not any(kw in str(og_title.get("content")).lower() for kw in ["captcha", "robot"]):
                    metadata["title"] = og_title["content"]
                elif raw_title:
                    # Limpa títulos da Amazon que vem com o sufixo da loja
                    metadata["title"] = raw_title.split(" | Amazon.com.br")[0].split(": Amazon.com.br:")[0]

                # Valida se o título extraído é útil
                extracted_title = str(metadata.get("title", ""))
                if any(kw in extracted_title.lower() for kw in ["503 - erro", "service unavailable", "robot check"]):
                    metadata["title"] = ""
                    if attempt < max_retries - 1: continue
                    else: break

                # Imagem
                og_image = soup.find("meta", property="og:image")
                if og_image and og_image.get("content"):
                    metadata["image_url"] = str(og_image["content"])
                
                # Fallbacks Amazon para imagem
                current_img = str(metadata.get("image_url", ""))
                if not current_img or "captcha" in current_img.lower():
                    img_tag = soup.find("img", id="landingImage") or soup.find("img", id="main-image")
                    if img_tag:
                        dyn_data = img_tag.get("data-a-dynamic-image")
                        if dyn_data:
                            try:
                                dyn_img = json.loads(str(dyn_data))
                                metadata["image_url"] = str(list(dyn_img.keys())[0]) if dyn_img else ""
                            except: pass
                        if not metadata.get("image_url"):
                            metadata["image_url"] = str(img_tag.get("data-old-hires") or img_tag.get("src") or "")

                if metadata.get("title") and not is_blocked:
                    print(f"✅ Sucesso na tentativa {attempt + 1}!")
                    
                    if metadata["image_url"]:
                        img_url = str(metadata["image_url"])
                        if img_url.startswith("//"): img_url = "https:" + img_url
                        try:
                            img_res = await s.get(img_url, timeout=10)
                            if img_res.status_code == 200:
                                # Garantir caminho absoluto
                                base_path = os.path.join(os.getcwd(), "downloads")
                                if not os.path.exists(base_path): os.makedirs(base_path)
                                
                                file_name = os.path.join(base_path, f"scraped_{random.randint(1000, 9999)}.jpg")
                                with open(file_name, "wb") as f:
                                    f.write(img_res.content)
                                metadata["local_image_path"] = file_name
                                print(f"📸 Imagem salva: {file_name}")
                        except Exception as e:
                            print(f"❌ Erro ao baixar imagem: {e}")
                    return metadata
                    
        except Exception as e:
            print(f"❌ Erro na tentativa {attempt + 1} com {browser}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
    
    return metadata

def extract_price(text: str) -> str | None:
    """Extrai o valor numérico de um texto (ex: R$ 1.200,50 -> 1200.50)."""
    if not text:
        return None
    match = re.search(r'(?:R\$\s?)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', text)
    if match:
        return match.group(1).replace('.', '').replace(',', '.')
    return None
