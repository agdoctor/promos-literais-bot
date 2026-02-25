from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
import os
import re
import asyncio
import random
import json
from typing import Dict, List, Any, Optional
from config import PROXY_URL

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
        # Remove tudo após o código MLB ou o fim da URL do produto
        if "?" in url:
            return url.split("?")[0]
10: 

    if "magazineluiza.com.br" in url or "magalu.com" in url:
        if "?" in url: return url.split("?")[0]

    # Fallback genérico: remove query params se forem muito longos
    if len(url) > 200 and "?" in url:
        return url.split("?")[0]
        
    return url

def get_random_browser() -> str:
    """Retorna um perfil de navegador aleatório suportado pelo curl_cffi."""
    return random.choice(["chrome110", "chrome116", "chrome120", "chrome124", "safari15_5"])

async def download_image(url: str, session: Optional[AsyncSession] = None) -> Optional[str]:
    """Downloads an image from a URL and returns the local path."""
    if not url:
        return None
    
    if url.startswith("//"):
        url = "https:" + url
        
    try:
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
            
        file_name = f"downloads/scraped_{random.randint(1000, 9999)}.jpg"
        
        if session:
            res = await session.get(url, timeout=15)
        else:
            async with AsyncSession(impersonate="chrome120") as s:
                res = await s.get(url, timeout=15)
                
        if res.status_code == 200:
            with open(file_name, "wb") as f:
                f.write(res.content)
            return file_name
    except Exception as e:
        print(f"❌ Erro ao baixar imagem ({url[:50]}...): {e}")
        
    return None

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
            async with AsyncSession(impersonate=browser, headers=common_headers) as s:
                # Referer ajuda em lojas como KaBuM/FastShop/Shopee
                if "kabum.com.br" in url:
                    s.headers.update({"Referer": "https://www.google.com/"})
                elif "amazon.com.br" in url:
                    s.headers.update({"Referer": "https://www.amazon.com.br/"})
                elif "shopee.com.br" in url:
                    s.headers.update({"Referer": "https://shopee.com.br/"})
                elif "aliexpress.com" in url:
                    s.headers.update({"Referer": "https://pt.aliexpress.com/"})

                proxy_dict = PROXY_URL if PROXY_URL else None
                response = await s.get(url, timeout=30, allow_redirects=True, proxy=proxy_dict)
                metadata["status_code"] = response.status_code
                
                if response.status_code != 200:
                    print(f"⚠️ Status {response.status_code} na tentativa {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        continue
                    else: break
                
                text = response.text
                soup = BeautifulSoup(text, 'html.parser')
                
                # 1. Tentar Título por diversos Seletores
                title = ""
                css_selectors = [
                    "#productTitle",
                    "meta[property='og:title']",
                    "meta[name='twitter:title']",
                    "h1",
                    ".product-title",
                    ".item-title",
                    "title"
                ]
                
                for selector in css_selectors:
                    tag = soup.select_one(selector)
                    if tag:
                        content = tag.get("content") if tag.name == "meta" else tag.text
                        if content and len(content.strip()) > 5:
                            title = content.strip()
                            
                            # Fix para "Seguir o autor" da Amazon
                            if title.lower() == "seguir o autor":
                                title = ""
                                continue
                                
                            # Limpeza de títulos (Remove ISBN de livros Amazon)
                            title = re.sub(r'\s*-\s*\d{10,13}\s*-\s*Livros na Amazon Brasil.*$', '', title, flags=re.IGNORECASE)
                            
                            for store in ["Amazon.com.br", "KaBuM!", "Mercado Livre", "Shopee Brasil", "Magazine Luiza"]:
                                title = title.split(f" | {store}")[0].split(f" - {store}")[0]
                            break

                # 2. Tentar Título em Scripts JSON+LD (Shopee/AliExpress/Casas Bahia)
                if not title or any(kw in title.lower() for kw in ["just a moment", "captcha", "robot"]):
                    scripts = soup.find_all("script", type="application/ld+json")
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, list): data = data[0]
                            if data.get("@type") == "Product":
                                title = data.get("name", title)
                                if not metadata["image_url"]:
                                    metadata["image_url"] = data.get("image", "")
                            elif "@graph" in data:
                                for item in data["@graph"]:
                                    if item.get("@type") == "Product":
                                        title = item.get("name", title)
                        except: pass

                # 3. Detectar bloqueios ou títulos genéricos inúteis
                low_title = title.lower()
                block_keywords = ["robot check", "captcha", "503 - erro", "service unavailable", "acesso negado", "forbidden", "just a moment"]
                generic_titles = ["shopee brasil", "shopee portugal", "aliexpress - pt", "amazon.com.br", "mercado livre brasil"]
                
                is_invalid = not title or any(kw in low_title for kw in block_keywords)
                if not is_invalid:
                    # Se o título for EXATAMENTE ou começar por um nome genérico de loja
                    if any(low_title.startswith(gt) or low_title == gt for gt in generic_titles):
                        is_invalid = True

                # --- NOVO: Fallback via API Shopee para metadados ---
                if is_invalid and "shopee.com.br" in url:
                    print("⚠️ Scraper bloqueado pela Shopee. Tentando API oficial para metadados...")
                    try:
                        from affiliate import get_shopee_product_info
                        shopee_info = await get_shopee_product_info(url)
                        if shopee_info and shopee_info.get("title"):
                            metadata["title"] = shopee_info["title"]
                            metadata["image_url"] = shopee_info.get("image", metadata["image_url"])
                            print(f"✅ Metadados recuperados via API Shopee: {metadata['title'][:50]}...")
                            is_invalid = False # Recuperado!
                    except Exception as e:
                        print(f"❌ Erro no fallback da API Shopee: {e}")

                if is_invalid:
                    print(f"🚫 Bloqueio ou título genérico detectado: '{title[:50]}'")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        continue
                    else: break

                metadata["title"] = title

                # 4. Tentar Imagem
                if not metadata["image_url"] or "captcha" in str(metadata["image_url"]).lower():
                    img_selectors = [
                        ("meta", {"property": "og:image"}),
                        ("meta", {"name": "twitter:image"}),
                        ("img", {"id": "landingImage"}), 
                        ("img", {"id": "main-image"}),   
                        ("img", {"class": "product-image"}),
                        ("img", {"class": "i-amphtml-fill-content"}) 
                    ]
                    
                    for tag_name, attrs in img_selectors:
                        tag = soup.find(tag_name, attrs)
                        if tag:
                            img_src = tag.get("content") or tag.get("data-a-dynamic-image") or tag.get("src")
                            if img_src:
                                if img_src.startswith("{"): 
                                    try: metadata["image_url"] = list(json.loads(img_src).keys())[0]
                                    except: pass
                                else:
                                    metadata["image_url"] = img_src
                                break

                # Finalização de sucesso
                if metadata["title"]:
                    print(f"✅ Sucesso na tentativa {attempt + 1}!")
                    if metadata["image_url"]:
                        metadata["local_image_path"] = await download_image(metadata["image_url"], session=s)
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
