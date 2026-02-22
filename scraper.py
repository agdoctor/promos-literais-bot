import httpx
from bs4 import BeautifulSoup
import os
import re
import asyncio
import random
import json
from typing import Dict, List, Any, Optional

try:
    from curl_cffi.requests import AsyncSession as CurlSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

def clean_amazon_url(url: str) -> str:
    """Limpa parâmetros de rastreio da Amazon."""
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    if match:
        asin = match.group(1)
        return f"https://www.amazon.com.br/dp/{asin}"
    return url

def clean_url(url: str) -> str:
    """Limpa parâmetros de rastreio de diversas lojas para evitar bloqueios por WAF."""
    if "amazon.com.br" in url:
        return clean_amazon_url(url)
    
    if "kabum.com.br" in url:
        # Padrão: /produto/ID/...
        match = re.search(r'(kabum\.com\.br/produto/\d+)', url)
        if match:
            return "https://www." + match.group(1)
            
    if "mercadolivre.com.br" in url:
        if "?" in url: return url.split("?")[0]

    if "magazineluiza.com.br" in url or "magalu.com" in url:
        if "?" in url: return url.split("?")[0]

    # Fallback genérico
    if len(url) > 200 and "?" in url:
        return url.split("?")[0]
        
    return url

def get_random_browser() -> str:
    """Retorna um perfil de navegador aleatório suportado pelo curl_cffi."""
    return random.choice(["chrome110", "chrome116", "chrome120", "chrome124", "safari15_5"])

async def fetch_product_metadata(url: str) -> dict:
    """
    Acessa a URL e tenta extrair o título do produto e a imagem principal usando curl_cffi
    para personificação de TLS de navegadores reais (bypass robusto).
    """
    url = clean_url(url)
    print(f"🔍 [SmartScraper TLS] Iniciando extração (URL Limpa): {url}")

    max_retries = 3
    metadata = {
        "title": "",
        "image_url": "",
        "local_image_path": "",
        "status_code": 200
    }

    # Headers comuns para evitar 403 de WAFs como Cloudflare
    common_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    for attempt in range(max_retries):
        browser = get_random_browser()
        print(f"🔄 Tentativa {attempt + 1}/{max_retries} usando personificação: {browser}")
        
        try:
            if HAS_CURL_CFFI:
                async with CurlSession(impersonate=browser, headers=common_headers) as s:
                    # Referer ajuda em algumas lojas
                    if "kabum.com.br" in url:
                        s.headers.update({"Referer": "https://www.google.com/"})
                    elif "amazon.com.br" in url:
                        s.headers.update({"Referer": "https://www.amazon.com.br/"})
                        
                    response = await s.get(url, timeout=20, allow_redirects=True)
                    text = response.text
                    status_code = response.status_code
            else:
                # Fallback para httpx
                async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
                    response = await client.get(url)
                    text = response.text
                    status_code = response.status_code
            
            metadata["status_code"] = status_code
            
            if status_code != 200:
                print(f"⚠️ Status {status_code} na tentativa {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    continue
                else:
                    return metadata
            
            soup = BeautifulSoup(text, 'html.parser')
            title_tag = soup.find("title")
            raw_title = title_tag.text.strip() if title_tag else ""
            
            # Detecta bloqueio real
            low_title = raw_title.lower().strip()
            is_blocked = False
            
            block_keywords = ["robot check", "captcha", "503 - erro", "service unavailable", "indisponível", "acesso negado", "forbidden", "just a moment"]
            if any(kw in low_title for kw in block_keywords):
                is_blocked = True
            
            if not is_blocked:
                generic_names = ["amazon.com.br", "mercado livre", "mercadolivre", "amazon", "kabum", "kabum!"]
                if low_title in generic_names or (len(low_title) < 25 and any(kw == low_title for kw in generic_names)):
                    is_blocked = True

            if is_blocked:
                print(f"🚫 Bloqueio real detectado no título: '{raw_title}'")
                if attempt < max_retries - 1:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    continue
                else:
                    metadata["title"] = ""
                    return metadata
            
            # Sucesso parcial: Tentar extrair dados
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content") and not any(kw in str(og_title.get("content")).lower() for kw in ["captcha", "robot"]):
                metadata["title"] = og_title["content"]
            elif raw_title:
                metadata["title"] = raw_title.split(" | Amazon.com.br")[0].split(": Amazon.com.br:")[0].split(" | KaBuM!")[0]

            extracted_title = str(metadata.get("title", ""))
            if any(kw in extracted_title.lower() for kw in ["503 - erro", "service unavailable", "robot check", "kabum", "amazon.com.br"]):
                metadata["title"] = ""
                if attempt < max_retries - 1: continue
                else: return metadata

            if metadata.get("title"):
                print(f"✅ Sucesso na tentativa {attempt + 1}!")
                
                # Imagem
                og_image = soup.find("meta", property="og:image")
                if og_image and og_image.get("content"):
                    metadata["image_url"] = str(og_image["content"])
                
                if metadata["image_url"]:
                    img_url = str(metadata["image_url"])
                    if img_url.startswith("//"): img_url = "https:" + img_url
                    try:
                        if HAS_CURL_CFFI:
                            async with CurlSession(impersonate=browser) as s:
                                img_res = await s.get(img_url, timeout=10)
                                img_content = img_res.content
                                img_status = img_res.status_code
                        else:
                            async with httpx.AsyncClient(timeout=10) as client:
                                img_res = await client.get(img_url)
                                img_content = img_res.content
                                img_status = img_res.status_code

                        if img_status == 200:
                            if not os.path.exists("downloads"): os.makedirs("downloads")
                            file_name = f"downloads/scraped_{random.randint(1000, 9999)}.jpg"
                            with open(file_name, "wb") as f:
                                f.write(img_content)
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
    """Extrai o valor numérico de um texto."""
    if not text:
        return None
    match = re.search(r'(?:R\$\s?)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', text)
    if match:
        return match.group(1).replace('.', '').replace(',', '.')
    return None
