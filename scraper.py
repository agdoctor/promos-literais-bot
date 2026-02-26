from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
import os
import re
import asyncio
import random
import json
import httpx
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
        match = re.search(r'(kabum\.com\.br/produto/\d+)', url)
        if match:
            return "https://www." + match.group(1)
            
    if "mercadolivre.com.br" in url:
        if "?" in url:
            return url.split("?")[0]

    if "magazineluiza.com.br" in url or "magalu.com" in url:
        if "?" in url: return url.split("?")[0]

    if len(url) > 300 and "?" in url:
        return url.split("?")[0]
        
    return url

async def expand_url(url: str) -> str:
    """Expande URLs curtas de Shopee e outras lojas."""
    if any(d in url for d in ['s.shopee', 'shope.ee', 'shopee.page.link', 't.me', 'bit.ly']):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(url)
                expanded = str(r.url)
                print(f"[Expand] {url} -> {expanded[:120]}")
                return expanded
        except Exception as e:
            print(f"[Expand] Falha ao expandir {url}: {e}")
    return url

def get_random_browser() -> str:
    """Retorna um perfil de navegador aleatório suportado pelo curl_cffi."""
    return random.choice(["chrome110", "chrome116", "chrome120", "chrome124", "safari15_5"])

async def download_image(url: str, session: Optional[AsyncSession] = None) -> Optional[str]:
    """Downloads an image from a URL and returns the local path."""
    if not url: return None
    if url.startswith("//"): url = "https:" + url
    try:
        if not os.path.exists("downloads"): os.makedirs("downloads")
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
    Extração robusta de metadados com bypass TLS e fallbacks múltiplos.
    """
    # 1. Expandir URL antes de tudo para o slug funcionar
    url = await expand_url(url)
    url = clean_url(url)
    
    print(f"🔍 [SmartScraper TLS] Iniciando extração: {url[:120]}")

    max_retries = 3
    metadata = {
        "title": "",
        "image_url": "",
        "local_image_path": "",
        "status_code": 200
    }

    # --- Pré-extrair título do slug (fallback garantido para Shopee) ---
    shopee_slug_title = None
    if "shopee.com.br" in url:
        try:
            path = url.split('?')[0].rstrip('/').split('/')[-1]
            slug = re.sub(r'-i\.\d+\.\d+$', '', path)
            candidate = slug.replace('-', ' ').strip()
            if len(candidate) > 8:
                shopee_slug_title = candidate
                print(f"[Shopee Slug] Pré-extraído: {shopee_slug_title[:60]}")
        except Exception:
            pass

    common_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
    }

    for attempt in range(max_retries):
        browser = get_random_browser()
        print(f"🔄 Tentativa {attempt + 1}/{max_retries} usando {browser}")
        try:
            async with AsyncSession(impersonate=browser, headers=common_headers) as s:
                if "shopee.com.br" in url: s.headers.update({"Referer": "https://shopee.com.br/"})
                
                proxy_dict = PROXY_URL if PROXY_URL else None
                response = await s.get(url, timeout=30, allow_redirects=True, proxy=proxy_dict)
                metadata["status_code"] = response.status_code
                
                if response.status_code != 200:
                    print(f"⚠️ Status {response.status_code} na tentativa {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        continue
                    else: break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 1. Extração de Título
                title = ""
                css_selectors = ["#productTitle", "meta[property='og:title']", "meta[name='twitter:title']", "h1", "title"]
                for selector in css_selectors:
                    tag = soup.select_one(selector)
                    if tag:
                        content = tag.get("content") if tag.name == "meta" else tag.text
                        if content and len(content.strip()) > 5:
                            title = content.strip()
                            for store in ["Amazon.com.br", "KaBuM!", "Mercado Livre", "Shopee Brasil", "Magazine Luiza"]:
                                title = title.split(f" | {store}")[0].split(f" - {store}")[0]
                            break

                # 2. Scripts LD+JSON
                if not title or any(kw in title.lower() for kw in ["moment", "captcha", "robot"]):
                    scripts = soup.find_all("script", type="application/ld+json")
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, list): data = data[0]
                            if data.get("@type") == "Product":
                                title = data.get("name", title)
                                if not metadata["image_url"]: metadata["image_url"] = data.get("image", "")
                        except: pass

                # 3. Detectar bloqueios
                low_title = title.lower()
                is_invalid = not title or any(kw in low_title for kw in ["robot check", "captcha", "503", "forbidden", "moment"])
                
                # --- Fallback Shopee API ---
                if is_invalid and "shopee.com.br" in url:
                    print("⚠️ Scraper bloqueado pela Shopee. Tentando API oficial...")
                    try:
                        from affiliate import get_shopee_product_info
                        shopee_info = await get_shopee_product_info(url)
                        if shopee_info and shopee_info.get("title"):
                            metadata["title"] = shopee_info["title"]
                            metadata["image_url"] = shopee_info.get("image", "") or ""
                            print(f"✅ Recuperado via API Shopee: {metadata['title'][:60]}")
                            if metadata["image_url"]: 
                                metadata["local_image_path"] = await download_image(metadata["image_url"])
                            return metadata
                        elif shopee_slug_title:
                            metadata["title"] = shopee_slug_title
                            print(f"✅ Recuperado via Shopee Slug: {metadata['title'][:60]}")
                            return metadata
                    except Exception as e:
                        print(f"❌ Erro fallback Shopee: {e}")

                if is_invalid:
                    print(f"🚫 Bloqueio detectado: '{title[:50]}'")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    else: break

                metadata["title"] = title

                # 4. Extração de Imagem
                if not metadata["image_url"] or "captcha" in str(metadata["image_url"]).lower():
                    img_selectors = [("meta", {"property": "og:image"}), ("img", {"id": "landingImage"}), ("img", {"class": "product-image"})]
                    for tag_name, attrs in img_selectors:
                        tag = soup.find(tag_name, attrs)
                        if tag:
                            img_src = tag.get("content") or tag.get("src")
                            if img_src: metadata["image_url"] = img_src; break

                if metadata["title"]:
                    if metadata["image_url"]:
                        metadata["local_image_path"] = await download_image(metadata["image_url"], session=s)
                    return metadata
                    
        except Exception as e:
            print(f"❌ Erro na tentativa {attempt + 1}: {e}")
            if attempt < max_retries - 1: await asyncio.sleep(1)
    
    # Fallback Final: Shopee Slug
    if not metadata["title"] and shopee_slug_title:
        metadata["title"] = shopee_slug_title
        print(f"[Shopee] Usando slug como último recurso: {shopee_slug_title}")
    
    return metadata

def extract_price(text: str) -> str | None:
    if not text: return None
    match = re.search(r'(?:R\$\s?)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', text)
    if match: return match.group(1).replace('.', '').replace(',', '.')
    return None
