import asyncio
import httpx
from bs4 import BeautifulSoup
import re

async def resolve_social_link(url: str) -> str:
    print(f"Resolvendo link social: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            response = await client.get(url)
            
            # Quando acessamos a página social de alguém, o ML pode fazer um redirect via JS ou Header, ou carregar o produto
            # Se for carregado diretamente, a URL será a do produto
            print(f"URL final após GET: {response.url}")
            
            # Se a URL continuou sendo /social/, procure por redirects na bagagem
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Procurar por window.location ou open app links no script
            # <meta property="og:url" content="https://produto.mercadolivre.com.br/..." />
            og_url = soup.find("meta", property="og:url")
            if og_url and "produto.mercadolivre" in og_url["content"]:
                print(f"URL OG encontrada: {og_url['content']}")
                return og_url["content"]
            
            # Procurar por canonical
            canonical = soup.find("link", rel="canonical")
            if canonical and "produto.mercadolivre" in canonical["href"]:
                print(f"URL Canonical encontrada: {canonical['href']}")
                return canonical["href"]
            
            return str(response.url)
            
    except Exception as e:
        print(f"Erro ao resolver link social: {e}")
        return url

async def test():
    social_url = "https://www.mercadolivre.com.br/social/nerdofertas?matt_word=admtokkyo&matt_tool=55107392&forceInApp=true&ref=BIo49aUw6yOjYOMUT0ocAvpU4k9Fom%2BqN7nIK6web6wP2%2FTIxMqZhiXf1PmsACVk2m27hIUwiuc%2BCG6u3Qj4SgOr%2Fl%2FoiH2qCx1S5yl2U0VPz5Tak6%2Bb8gT6m5Bh5Hs3FSITW8x1HtRHFJXDHDFV4nOZNtg4K1%2BWbwdrY98fct%2F4t1DKubp3L1luSOYyfNoLAtp6MDM%3D"
    print(f"Buscando HTML para: {social_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
        response = await client.get(social_url)
        with open("ml_social_dump.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"Salvo em ml_social_dump.html (Tamanho: {len(response.text)} bytes)")

asyncio.run(test())


