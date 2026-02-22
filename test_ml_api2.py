import asyncio
import httpx
from config import ML_AFFILIATE_COOKIE

async def main():
    url = "https://www.mercadolivre.com.br/tv-box-aquario-plus-4k-stv-3000-plus-stv-3000-4k-padro-4k-16gb-preto-com-2gb-de-memoria-ram/p/MLB35587178#reco_backend=item_decorator&reco_client=home_affiliate-profile&reco_item_pos=0&source=affiliate-profile&reco_backend_type=function&reco_id=e71ba3ab-1865-4426-8fd6-b8fe435ce57d&tracking_id=a71ea424-291f-4398-9ee0-82f3da6a70a5&c_id=/home/card-featured/element&c_uid=379732a9-2adf-4ff4-b26b-538ec061304a"
    payload = {"url": url, "tag": "drmkt"}
    
    print(f"--- TESTANDO PAYLOAD EXATO DO SUBAGENT ---")
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
