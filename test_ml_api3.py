import asyncio
import httpx
from config import ML_AFFILIATE_COOKIE

async def main():
    # URL sem #reco e ?tracking_id
    url = "https://www.mercadolivre.com.br/tv-box-aquario-plus-4k-stv-3000-plus-stv-3000-4k-padro-4k-16gb-preto-com-2gb-de-memoria-ram/p/MLB35587178"
    payload = {"url": url, "tag": "drmkt"}
    
    print(f"--- TESTANDO URL LIMPA ---")
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

if __name__ == "__main__":
    asyncio.run(main())
