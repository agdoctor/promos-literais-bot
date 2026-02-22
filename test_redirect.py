import httpx
res = httpx.get('https://mercadolivre.com/sec/31KLaXr', follow_redirects=True)
print(res.url)
