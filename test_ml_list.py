import httpx
import asyncio
import re

async def main():
    url = "https://mercadolivre.com/sec/2RNyYZM"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
        res = await client.get(url)
        print(f"URL: {res.url}")
        
        # O link na verdade fica dentro do JSON de estado: "seeMoreLink":"https:\/\/lista.mercadolivre.com.br\/..."
        match = re.search(r'"seeMoreLink":"([^"]+)"', res.text)
        if match:
            raw_link = match.group(1)
            # Remove os escapes das barras (\/)
            clean_link = raw_link.replace('\\/', '/')
            print("Encontrei o List Link:", clean_link)
        else:
            print("Não achei nadinha.")
            
if __name__ == "__main__":
    asyncio.run(main())
