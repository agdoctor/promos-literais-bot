import asyncio
import httpx

async def expand_url(short_url: str) -> str:
    try:
        # User-Agent é obrigatório para evitar bloqueios do Mercado Livre
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            response = await client.get(short_url)
            return str(response.url)
    except Exception as e:
        print(f"Erro ao expandir URL {short_url}: {e}")
        return short_url

async def test():
    urls = [
        "https://mercadolivre.com/sec/1zkWkAe",
        "https://amzn.to/3P8YJ1T"
    ]
    for u in urls:
        print(f"Original: {u}")
        print(f"Expandido: {await expand_url(u)}")

asyncio.run(test())
