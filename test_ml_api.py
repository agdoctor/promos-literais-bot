import asyncio
import httpx
from config import ML_AFFILIATE_COOKIE

async def test_api(url, payload):
    print(f"--- TESTANDO ML PAYLOAD ---")
    print(f"Payload: {payload}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                'Content-Type': 'application/json',
                'Cookie': ML_AFFILIATE_COOKIE,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://www.mercadolivre.com.br',
                'Referer': url,
            }
            
            response = await client.post(
                'https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links',
                headers=headers,
                json=payload,
                follow_redirects=False
            )
            print(f"Status: {response.status_code}")
            print(f"Resposta: {response.text}")
    except Exception as e:
        print(f"Erro: {e}")

async def main():
    url = "https://www.mercadolivre.com.br/apple-iphone-15-128-gb-preto/p/MLB27581501"
    
    # 1. Array of urls
    await test_api(url, {"urls": [url], "tag": "drmkt"})
    # 2. Singular url without tag
    await test_api(url, {"url": url})
    # 3. Old URL format with drmkt
    old_url = "https://produto.mercadolivre.com.br/MLB-27581501-apple-iphone-15-128-gb-preto-_JM"
    await test_api(old_url, {"url": old_url, "tag": "drmkt"})

if __name__ == "__main__":
    asyncio.run(main())
