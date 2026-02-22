import asyncio
import httpx
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, parse_qs, unquote
from config import ML_AFFILIATE_COOKIE
from affiliate import clean_tracking_params

async def test_end_to_end():
    # 1. Start with the shortlink user pasted
    ml_link = "https://mercadolivre.com/sec/1zkWkAe"
    print(f"1. Original curto: {ml_link}")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
        # 2. Expand it to get the /social/ vitrine link
        res = await client.get(ml_link)
        expanded = str(res.url)
        print(f"2. Expandido (Vitrine): {expanded}")
        
        parsed = urlparse(expanded)
        if '/social/' in parsed.path:
            # 3. Fetch the vitrine HTML to find the 'Ir para o produto' link
            print("3. Analisando HTML da vitrine para achar o produto...")
            soup = BeautifulSoup(res.text, 'html.parser')
            featured_link = soup.select_one("a.poly-component__link--action-link")
            
            # Fallback for regex if class changes
            if not featured_link:
                featured_link = soup.find("a", href=re.compile("card-featured"))
                
            if featured_link and featured_link.get("href"):
                product_url = featured_link['href']
                print(f"4. Produto Encontrado: {product_url}")
                
                # 5. Clean the tracking params and hit the API
                clean_url = clean_tracking_params(product_url)
                print(f"5. URL limpa pronta para conversão: {clean_url}")
                
                payload = {"url": clean_url, "tag": "drmkt"}
                api_headers = {
                    'Content-Type': 'application/json',
                    'Cookie': ML_AFFILIATE_COOKIE,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Origin': 'https://www.mercadolivre.com.br',
                    'Referer': clean_url,
                }
                
                # USE UM NOVO CLIENTE PARA EVITAR CONFLITO DE COOKIES
                print("5. URL limpa pronta para conversão. Chamando API Stripe...")
                async with httpx.AsyncClient(timeout=10.0) as api_client:
                    res_api = await api_client.post(
                        'https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links',
                        headers=api_headers, json=payload, follow_redirects=False)
                    
                    if res_api.status_code == 200:
                        data = res_api.json()
                        short = data.get('short_url') or data.get('url')
                        print(f"6. ✅ SUCESSO! Link de Afiliado Gerado: {short}")
                    else:
                        print(f"6. ❌ ERRO NA API: {res_api.status_code} - {res_api.text}")
            else:
                print("❌ Não foi possível encontrar o botão 'Ir para o produto' na vitrine.")
        else:
            print("❌ O link expandido não era uma vitrine social.")

asyncio.run(test_end_to_end())
