import asyncio
import httpx
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, unquote
from config import ML_AFFILIATE_COOKIE
from affiliate import clean_tracking_params

async def test_full_flow():
    ml_link = "https://mercadolivre.com/sec/1zkWkAe"
    print(f"Original curto: {ml_link}")
    
    # 1. Expand
    headers = {'User-Agent': 'Mozilla/5.0'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
        res = await client.get(ml_link)
        expanded = str(res.url)
        
        print(f"Expandido: {expanded}")
        
        # 2. Extract ref
        parsed = urlparse(expanded)
        if '/social/' in parsed.path:
            query_params = parse_qs(parsed.query)
            if 'ref' in query_params:
                extracted_ref = unquote(query_params['ref'][0])
                print(f"Extracted Ref: {extracted_ref}")
                # Try to hit API directly with extracted ref WITHOUT cleaning
                
                payload = {"url": extracted_ref, "tag": "drmkt"}
                api_headers = {
                    'Content-Type': 'application/json',
                    'Cookie': ML_AFFILIATE_COOKIE,
                    'User-Agent': 'Mozilla/5.0',
                }
                res2 = await client.post(
                    'https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links',
                    headers=api_headers, json=payload, follow_redirects=False)
                
                print(f"API RAW Status: {res2.status_code}")
                if res2.status_code == 200:
                    print(f"API RAW Result: {res2.json().get('short_url')}")
                else:
                    print(f"API RAW ERROR: {res2.text}")
                    
                # Try hitting API with cleaned ref
                cleaned = clean_tracking_params(extracted_ref)
                print(f"Cleaned URL: {cleaned}")
                
                payload2 = {"url": cleaned, "tag": "drmkt"}
                res3 = await client.post(
                    'https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links',
                    headers=api_headers, json=payload2, follow_redirects=False)
                    
                print(f"API CLEAN Status: {res3.status_code}")
                if res3.status_code == 200:
                    print(f"API CLEAN Result: {res3.json().get('short_url')}")
                else:
                    print(f"API CLEAN ERROR: {res3.text}")

asyncio.run(test_full_flow())
