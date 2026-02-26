import httpx
import asyncio
from config import ML_AFFILIATE_COOKIE
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, unquote
from bs4 import BeautifulSoup
import re
import hashlib
import hmac
import time
import json
from datetime import datetime
from config import PROXY_URL

def clean_tracking_params(url: str) -> str:
    """
    Remove parmetros de rastreamento conhecidos para evitar conflitos e links sujos.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Lista de parmetros para remover
        params_to_remove = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'smid', 'pf_rd_p', 'pf_rd_r', 'pd_rd_w', 'pd_rd_wg', 'pd_rd_r',
            'dchild', 'keywords', 'qid', 'sr', 'th', 'psc', 'sp_atk', 'is_from_signup',
            'matt_tool', 'matt_word', 'product_trigger_id', 'gad_source', 'gbraid', 'gclid'
        ]
        
        filtered_params = {k: v for k, v in params.items() if k not in params_to_remove}
        
        # Recompor a URL
        new_query = urlencode(filtered_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception as e:
        print(f"[!] Erro ao limpar parametros: {e}")
        return url

async def convert_ml_to_affiliate(original_url: str) -> str:
    """
    Converte um link do Mercado Livre em link de afiliado usando a Stripe API.
    Lida com links de vitrine (/social/) extraindo o produto destacado.
    """
    import config
    from database import get_config
    ml_cookie = get_config("ML_AFFILIATE_COOKIE") or getattr(config, 'ML_AFFILIATE_COOKIE', None)
    if not ml_cookie:
        print("[!] ML_AFFILIATE_COOKIE nao configurado. Configure no Painel > Afiliados.")
        return original_url

    parsed = urlparse(original_url)
    target_product_url = original_url

    # Se a URL for uma vitrine social de um concorrente (ex: /social/nerdofertas), 
    # precisamos acessar a vitrine e raspar a URL do produto destacado.
    if '/social/' in parsed.path:
        print(f"[SEARCH] Link Social (Vitrine) detectado: {original_url}")
        try:
            # Reutiliza httpx para baixar a vitrine
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
                res = await client.get(original_url)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 1. Tentar encontrar link de Lista Curada (seeMoreLink com _Container_)
                match_list = re.search(r'"seeMoreLink":"([^"]+lista\.mercadolivre\.com\.br\\u002F_Container_[^"]+)"', res.text)
                if not match_list:
                    match_list = re.search(r'"seeMoreLink":"([^"]+)"', res.text)
                
                if match_list and 'lista.mercadolivre.com.br' in match_list.group(1):
                    raw_link = match_list.group(1)
                    # O JSON escapa as barras como \u002F ou \/
                    target_product_url = raw_link.replace('\\u002F', '/').replace('\\/', '/')
                    print(f"[OK] Lista curada extraida da vitrine: {target_product_url}")
                else:
                    # 2. Se no for lista, tentar achar o produto em destaque usual
                    # O produto destacado no topo tem a classe poly-component__link--action-link
                    featured_link = soup.select_one("a.poly-component__link--action-link")
                    if not featured_link:
                        # Fallback via url
                        featured_link = soup.find("a", href=re.compile("card-featured"))
                        
                    if featured_link and featured_link.get("href"):
                        target_product_url = featured_link['href']
                        print(f"Produto extraido da vitrine: {target_product_url}")
                    else:
                        print(f"[ERR] Nao foi possivel encontrar o produto destacado ou lista na vitrine.")
        except Exception as e:
            print(f"[!] Erro ao acessar vitrine social: {e}")

    # Limpar a URL do produto antes de enviar para a API
    clean_url = clean_tracking_params(target_product_url)

    # Se a API falhar, o fallback  passar a URL original inteira (ou limpa) no ref do nosso link social genrico
    fallback_social_url = f"https://www.mercadolivre.com.br/social/drmkt?forceInApp=true&matt_word=drmk&ref={clean_url}"

    try:
        print(f"Convertendo ML via API Stripe: {clean_url}")
        # A API Stripe exige um NOVO cliente httpx para no enviar _csrf cookies das requisies anteriores
        async with httpx.AsyncClient(timeout=10.0) as api_client:
            api_headers = {
                'Content-Type': 'application/json',
                'Cookie': ml_cookie,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://www.mercadolivre.com.br',
                'Referer': clean_url,
            }
            body = {
                'url': clean_url,
                'tag': 'drmkt'
            }
            
            response = await api_client.post(
                'https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links',
                headers=api_headers,
                json=body,
                follow_redirects=False
            )

            if response.status_code >= 300 and response.status_code < 400:
                print(f"[ERR] API do ML redirecionou (provavelmente cookie expirado): {response.headers.get('location')}")
                return fallback_social_url

            if response.status_code != 200:
                print(f"[ERR] Erro na API do ML ({response.status_code}): {response.text}")
                return fallback_social_url

            data = response.json()
            if isinstance(data, dict):
                short_url = data.get('url') or data.get('short_url')
                if short_url: return short_url
            elif isinstance(data, list) and len(data) > 0:
                short_url = data[0].get('short_url')
                if short_url: return short_url

            return fallback_social_url

    except Exception as e:
        print(f"[!] Erro ao gerar link de afiliado ML: {e}")
        return fallback_social_url

async def convert_aliexpress_to_affiliate(original_url: str) -> str:
    """
    Converte um link do AliExpress para link de afiliado usando a API oficial (Open Platform).
    """
    import config
    from database import get_config
    ALI_APP_KEY = get_config("ALI_APP_KEY") or getattr(config, 'ALI_APP_KEY', None)
    ALI_APP_SECRET = get_config("ALI_APP_SECRET") or getattr(config, 'ALI_APP_SECRET', None)
    ALI_TRACKING_ID = get_config("ALI_TRACKING_ID") or getattr(config, 'ALI_TRACKING_ID', None)

    # Normalizar URL: se for um link sujo de moedas (coin-index) com productIds na URL, a gente limpa
    clean_url = original_url
    if "productIds=" in original_url:
        match = re.search(r'productIds=(\d+)', original_url)
        if match:
            pid = match.group(1)
            clean_url = f"https://pt.aliexpress.com/item/{pid}.html"
            print(f"[!] URL suja do AliExpress detectada. ID {pid} isolado: {clean_url}")
    elif "item/" in original_url:
        match = re.search(r'item/(\d+)\.html', original_url)
        if match:
            pid = match.group(1)
            clean_url = f"https://pt.aliexpress.com/item/{pid}.html"
            print(f"[!] URL AliExpress limpa: {clean_url}")
            
    clean_url = clean_tracking_params(clean_url)
    
    if not ALI_APP_KEY or not ALI_APP_SECRET or not ALI_TRACKING_ID:
        print("[!] Credenciais da API AliExpress nao configuradas. Usando gerador generico de deeplink.")
        if ALI_TRACKING_ID:
            import urllib.parse
            encoded_url = urllib.parse.quote(clean_url, safe='')
            return f"https://s.click.aliexpress.com/deep_link.htm?aff_short_key={ALI_TRACKING_ID}&dl_target_url={encoded_url}"
        return clean_url

    def get_fallback_url(url: str) -> str:
        if ALI_TRACKING_ID:
            import urllib.parse
            encoded = urllib.parse.quote(url, safe='')
            return f"https://s.click.aliexpress.com/deep_link.htm?aff_short_key={ALI_TRACKING_ID}&dl_target_url={encoded}"
        return url

    
    # Parmetros obrigatrios da API TopClient AliExpress
    params = {
        "method": "aliexpress.affiliate.link.generate",
        "app_key": ALI_APP_KEY,
        "sign_method": "md5",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "promotion_link_type": "0",
        "source_values": clean_url,
        "tracking_id": ALI_TRACKING_ID
    }
    
    # Algoritmo de Assinatura (MD5) da plataforma
    # 1. Ordenar parmetros em ordem alfabtica pela chave
    sorted_keys = sorted(params.keys())
    # 2. String = SECRET_KEY + key1 + value1 + key2 + value2 ... + SECRET_KEY
    sign_str = ALI_APP_SECRET
    for k in sorted_keys:
        sign_str += str(k) + str(params[k])
    sign_str += ALI_APP_SECRET
    
    # 3. MD5 hash em Maisculo
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()
    params["sign"] = sign

    try:
        print(f"Convertendo AliExpress via API Oficial: {clean_url}")
        async with httpx.AsyncClient(timeout=10.0) as api_client:
            response = await api_client.post(
                "https://api-sg.aliexpress.com/sync",
                data=params, # enviar como form-data
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
            )
            
            if response.status_code != 200:
                print(f"[ERR] Erro na API do AliExpress ({response.status_code}): {response.text}")
                return get_fallback_url(clean_url)
                
            data = response.json()
            
            # Formato de resposta esperado: 
            # {"aliexpress_affiliate_link_generate_response": {
            #    "resp_result": { "result": { "promoted_links": { "promoted_link": [{"promotion_link": "..."}]}}}
            # }}
            
            try:
                base_resp = data.get("aliexpress_affiliate_link_generate_response", {})
                resp_result = base_resp.get("resp_result", {})
                
                # O resp_code pode vir como int ou str
                resp_code = str(resp_result.get("resp_code", ""))
                if resp_code != "200":
                    print(f"[ERR] API do AliExpress retornou erro na resposta interna: {resp_result}")
                    return get_fallback_url(clean_url)
                    
                result = resp_result.get("result", {})
                promotion_links = result.get("promotion_links", {}).get("promotion_link", [])
                
                if promotion_links and len(promotion_links) > 0:
                    item_info = promotion_links[0]
                    short_url = item_info.get("promotion_link")
                    if short_url:
                        return short_url
                    else:
                        print(f" Erro ao converter item no AliExpress: {item_info.get('message', 'Desconhecido')}")
                else:
                    print("[!] Modulo promotion_links vazio na resposta.")
                        
            except Exception as parse_err:
                print(f" Erro ao analisar resposta do AliExpress: {parse_err}. Retorno bruto: {data}")
                return get_fallback_url(clean_url)

    except Exception as e:
        print(f"[!] Erro ao gerar link de afiliado AliExpress: {e}")
        
    return get_fallback_url(clean_url)

async def shorten_url_tiny(long_url: str) -> str:
    """Encurtador de URL via TinyURL pblico."""
    import urllib.parse
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            encoded_url = urllib.parse.quote(long_url)
            res = await client.get(f"https://tinyurl.com/api-create.php?url={encoded_url}")
            if res.status_code == 200 and res.text.startswith("http"):
                return res.text
    except Exception as e:
        print(f"[!] Erro ao encurtar URL ({long_url[:30]}...): {e}")
    return long_url

async def convert_shopee_to_affiliate(original_url: str) -> str:
    """
    Converte um link da Shopee para link de afiliado usando a API oficial (Open Platform V2).
    """
    import config
    from database import get_config
    import hmac
    import hashlib
    import time
    import json
    
    # Prioriza banco de dados, fallback para config.py / .env
    SHOPEE_APP_ID = get_config("SHOPEE_APP_ID") or getattr(config, 'SHOPEE_APP_ID', None)
    SHOPEE_APP_SECRET = get_config("SHOPEE_APP_SECRET") or getattr(config, 'SHOPEE_APP_SECRET', None)
    
    # 1. Limpar a URL
    clean_url_str = clean_tracking_params(original_url)
    
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        print("[!] Credenciais da API Shopee (AppID/Secret) nao configuradas. Verifique o Painel Web ou Environment.")
        return await convert_shopee_fallback_manual(original_url)

    # Endpoint da API Shopee (BR)
    url = "https://open-api.affiliate.shopee.com.br/graphql"
    
    # Payload GraphQL Oficial
    query = 'mutation { generateShortLink(input: { originUrl: "' + clean_url_str + '" }) { shortLink } }'
    body = json.dumps({"query": query}, separators=(',', ':'))
    timestamp = int(time.time())
    
    # Algoritmo Oficial: SHA256(AppId + Timestamp + Body + Secret)
    base_str = f"{SHOPEE_APP_ID}{timestamp}{body}{SHOPEE_APP_SECRET}"
    signature = hashlib.sha256(base_str.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Signature={signature}, Timestamp={timestamp}"
    }

    try:
        print(f"Convertendo Shopee via API Oficial: {clean_url_str}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, content=body)
            
            if response.status_code != 200:
                print(f"[ERR] Erro na API do Shopee ({response.status_code}): {response.text}")
                return await convert_shopee_fallback_manual(original_url)
                
            data = response.json()
            
            if "errors" in data:
                print(f"[ERR] Erro GraphQL Shopee: {data['errors']}")
                return await convert_shopee_fallback_manual(original_url)
                
            short_url = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
            if short_url:
                print(f"[OK] Link Shopee convertido via API Oficial: {short_url}")
                return short_url
                
    except Exception as e:
        print(f"[!] Erro de conexao com API Shopee: {e}")
        
    return await convert_shopee_fallback_manual(original_url)

async def convert_shopee_fallback_manual(original_url: str) -> str:
    """Logica antiga de fallback baseada em Universal Link (sem TinyURL agora)."""
    import config
    SHOPEE_AFFILIATE_ID = getattr(config, 'SHOPEE_AFFILIATE_ID', None)
    SHOPEE_SOURCE_ID = getattr(config, 'SHOPEE_SOURCE_ID', None)
    
    if not SHOPEE_AFFILIATE_ID:
        return clean_tracking_params(original_url)

    shop_id = None
    item_id = None
    
    match1 = re.search(r'shopee\.com\.br/product/(\d+)/(\d+)', original_url)
    if match1:
        shop_id = match1.group(1)
        item_id = match1.group(2)
    else:
        match2 = re.search(r'-i\.(\d+)\.(\d+)', original_url)
        if match2:
            shop_id = match2.group(1)
            item_id = match2.group(2)
            
    if shop_id and item_id:
        source_id = SHOPEE_SOURCE_ID if SHOPEE_SOURCE_ID else "python_bot"
        # Mantemos o linl shopee direto para evitar TinyURL no fallback tambem
        aff_url = (
            f"https://shopee.com.br/universal-link/product/{shop_id}/{item_id}"
            f"?utm_medium=affiliates&utm_source=an_{source_id}&utm_campaign=-&utm_content={SHOPEE_AFFILIATE_ID}"
        )
        return aff_url
        
    return clean_tracking_params(original_url)

async def get_shopee_product_info(url: str):
    """
    Busca informaes detalhadas do produto Shopee com mltiplas estratgias:
    1. Extrai ttulo do slug da URL (instantneo, sem API)
    2. API REST pblica da Shopee /api/v4/item/get (sem autenticao)
    3. API Affiliate GraphQL (requer credenciais)
    """
    import json, time, hashlib

    # --- Expandir links curtos ---
    working_url = url
    if any(d in url for d in ['s.shopee', 'shope.ee', 'shopee.page.link']):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
                r = await c.get(url)
                working_url = str(r.url)
                print(f"[Shopee] URL expandida: {working_url[:120]}")
        except Exception as e:
            print(f"[Shopee] Falha ao expandir URL curta: {e}")

    # --- Extrair shop_id e item_id ---
    shop_id, item_id = None, None
    m = re.search(r'-i\.(\d+)\.(\d+)', working_url)
    if m:
        shop_id, item_id = m.group(1), m.group(2)
    if not item_id:
        m = re.search(r'shopee\.com\.br/[^?]*/(\d+)/(\d+)', working_url)
        if m:
            shop_id, item_id = m.group(1), m.group(2)
    if not item_id:
        m = re.search(r'[?&]itemid=(\d+).*[?&]shopid=(\d+)', working_url, re.IGNORECASE)
        if m:
            item_id, shop_id = m.group(1), m.group(2)

    print(f"[Shopee] shop_id={shop_id} item_id={item_id}")

    # === ESTRATGIA 1: Ttulo via slug da URL ===
    slug_title = None
    try:
        # Padres possveis:
        # A. shopee.com.br/Nome-do-Produto-i.123.456
        # B. shopee.com.br/product/123/456
        # C. shopee.com.br/nome-do-vendedor-ou-produto/123/456
        path_segments = working_url.split('?')[0].rstrip('/').split('/')
        last_part = path_segments[-1]
        
        # Tenta remover o sufixo -i... (Padro A)
        slug = re.sub(r'-i\.\d+\.\d+$', '', last_part)
        
        # Se o resultado for numrico (Padro B ou C), o slug est antes dos IDs
        if slug.isdigit() and len(path_segments) >= 4:
            # Em /slug/shop/item, o slug est 2 posies atrs do item_id
            # path_segments: ["https:", "", "shopee.com.br", "SLUG", "SHOP", "ITEM"]
            candidate = path_segments[-3]
            if candidate != "product":
                slug = candidate
        
        if slug and not slug.isdigit():
            slug_title = slug.replace('-', ' ').strip()
            if len(slug_title) > 3:
                print(f"[Shopee Slug] Ttulo extrado: {slug_title[:80]}")
            else:
                slug_title = None
    except Exception:
        slug_title = None

    # === ESTRATGIA 2: API REST pblica da Shopee (sem auth) ===
    rest_result = None
    if item_id and shop_id:
        try:
            headers_rest = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'https://shopee.com.br/product/{shop_id}/{item_id}',
                'Accept': 'application/json',
                'x-api-source': 'pc',
                'x-shopee-language': 'pt-BR',
                'x-requested-with': 'XMLHttpRequest'
            }
            # Endpoint pdp/get_pc o que o desktop usa para carregar nome e imagem
            rest_url = f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}"
            # Correct proxy usage for httpx (string, not dict)
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, proxy=PROXY_URL) as client:
                resp = await client.get(rest_url, headers=headers_rest)
                print(f"[Shopee PDP API] Status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    item_data = data.get('data', {}).get('item', {}) or data.get('data', {}) or data.get('item', {})
                    name = item_data.get('name') or item_data.get('title') or item_data.get('item_name')
                    image = item_data.get('image') or item_data.get('images', [None])[0]
                    if name:
                        result = {
                            "title": name,
                            "image": f"https://down-br.img.susercontent.com/file/{image}" if image else None,
                            "price": str(item_data.get('price', 0) / 100000) if item_data.get('price') else "0"
                        }
                        print(f"[Shopee PDP] Sucesso: {result['title'][:50]}")
                        return result
        except Exception as e:
            print(f"[Shopee REST] Erro: {e}")

    if rest_result:
        return rest_result

    # === ESTRATGIA 3: API Affiliate GraphQL (schema correto) ===
    # Nota: productOfferV2 retorna ofertas do afiliado. Para buscar por item,
    # a query correta  productDetailByItemId (se disponvel) ou via productOffer
    try:
        import config
        from database import get_config as _gc
        app_id = _gc("SHOPEE_APP_ID") or getattr(config, 'SHOPEE_APP_ID', None)
        app_secret = _gc("SHOPEE_APP_SECRET") or getattr(config, 'SHOPEE_APP_SECRET', None)

        if app_id and app_secret and item_id:
            # Query simplificada para evitar erros de schema desconhecido
            query = """
            query {
              productOfferV2(keyword: \"""" + str(item_id) + """\") {
                nodes {
                  imageUrl
                  itemId
                  productName
                }
              }
            }
            """
            body = json.dumps({"query": query}, separators=(',', ':'))
            timestamp = int(time.time())
            base_str = f"{app_id}{timestamp}{body}{app_secret}"
            signature = hashlib.sha256(base_str.encode('utf-8')).hexdigest()
            gql_headers = {
                "Content-Type": "application/json",
                "Authorization": f"SHA256 Credential={app_id}, Signature={signature}, Timestamp={timestamp}"
            }
            async with httpx.AsyncClient(timeout=15.0, proxy=PROXY_URL) as client:
                resp = await client.post("https://open-api.affiliate.shopee.com.br/graphql",
                                         headers=gql_headers, content=body)
                print(f"[Shopee GQL] Status: {resp.status_code} | {resp.text[:300]}")
                if resp.status_code == 200:
                    data = resp.json()
                    gql_data = data.get("data", {}).get("productOfferV2", {})
                    if gql_data and "nodes" in gql_data:
                        nodes = gql_data.get("nodes", [])
                        node = next((n for n in nodes if str(n.get('itemId')) == str(item_id)), None)
                        if not node and nodes: node = nodes[0]
                        if node and node.get("productName"):
                            print(f"[Shopee GQL] Sucesso: {node['productName'][:50]}")
                            return {"title": node.get("productName"), "image": node.get("imageUrl")}
            # Fallback: se nodes veio vazio, tenta pesquisar pelo slug_title
            if not gql_data.get("nodes") and slug_title:
                print(f"[Shopee GQL] Tentando fallback por titulo: {slug_title}")
                query = """
                query {
                  productOfferV2(keyword: \"""" + slug_title + """\") {
                    nodes {
                      imageUrl
                      itemId
                      productName
                    }
                  }
                }
                """
                body = json.dumps({"query": query}, separators=(',', ':'))
                # Re-sign and post (simplified for brevity here)
                base_str = f"{app_id}{timestamp}{body}{app_secret}"
                signature = hashlib.sha256(base_str.encode('utf-8')).hexdigest()
                gql_headers["Authorization"] = f"SHA256 Credential={app_id}, Signature={signature}, Timestamp={timestamp}"
                
                async with httpx.AsyncClient(timeout=15.0, proxy=PROXY_URL) as client:
                    resp = await client.post("https://open-api.affiliate.shopee.com.br/graphql",
                                             headers=gql_headers, content=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        gql_data = data.get("data", {}).get("productOfferV2", {})
                        if gql_data and gql_data.get("nodes"):
                            nodes = gql_data.get("nodes", [])
                            node = nodes[0]
                            print(f"[Shopee GQL Fallback] Sucesso via Título: {node['productName'][:50]}")
                            return {"title": node.get("productName"), "image": node.get("imageUrl")}

    except Exception as e:
        print(f"[Shopee GQL] Erro: {e}")

    # === FALLBACK FINAL 1: Usar ttulo do slug se disponvel ===
    if slug_title:
        print(f"[Shopee] Usando ttulo do slug como fallback: {slug_title[:60]}")
        return {"title": slug_title, "image": None}

    # === FALLBACK FINAL 2: Google Search Snippet (ltimo recurso) ===
    if item_id and shop_id:
        google_res = await google_shopee_fallback(shop_id, item_id)
        if google_res:
            return google_res

    return None

async def google_shopee_fallback(shop_id, item_id):
    """
    Busca o nome do produto via Google Search snippets para links bloqueados.
    Tenta multiplas queries para maximizar chance de acerto.
    """
    queries = [
        f"shopee.com.br i.{shop_id}.{item_id}",
        f"site:shopee.com.br product/{shop_id}/{item_id}",
        f"shopee {item_id}"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }
    for q in queries:
        try:
            print(f"[Shopee Google Fallback] Tentando query: {q}")
            url = f"https://www.google.com/search?q={q}"
            async with httpx.AsyncClient(timeout=10.0, proxy=PROXY_URL, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # Tenta h3 (titulos de resultados)
                    for h3 in soup.find_all('h3'):
                        text = h3.get_text().strip()
                        if "Shopee" in text:
                            clean = re.split(r'\s*[|\-]\s*Shopee', text, flags=re.IGNORECASE)[0].strip()
                            if len(clean) > 8: 
                                print(f"[Shopee Google] Sucesso: {clean}")
                                return {"title": clean, "image": None}
                    
                    # Fallback no titulo da pagina
                    page_title = soup.title.string if soup.title else ""
                    if "Shopee" in page_title and len(page_title) > 20:
                        clean = re.split(r'\s*[|\-]\s*Shopee', page_title, flags=re.IGNORECASE)[0].strip()
                        if len(clean) > 8: return {"title": clean, "image": None}
            
            await asyncio.sleep(1) # Pequena pausa entre queries
        except Exception as e:
            print(f"[Shopee Google] Erro na query '{q}': {e}")
            
    return None


async def convert_to_affiliate(url: str) -> str:
    """
    Identifica a loja e aplica a lgica de converso correspondente.
    """
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return url
        domain = parsed.hostname.replace('www.', '').lower()
    except:
        return url

    # Mercado Livre
    if 'mercadolivre.com' in domain or 'mercadolibre.com' in domain:
        return await convert_ml_to_affiliate(url)
    
    # Amazon
    if 'amazon.com.br' in domain or 'amazon.com' in domain:
        import config
        from database import get_config
        AMAZON_TAG = get_config("AMAZON_TAG") or getattr(config, 'AMAZON_TAG', '')
        
        # Tenta extrair o ASIN (10 caracteres alfanumricos)
        # Padres comuns: /dp/ASIN, /gp/product/ASIN, /exec/obidos/ASIN
        asin_match = re.search(r'/(?:dp|gp/product|exec/obidos|aw/d)/([A-Z0-9]{10})', url, re.IGNORECASE)
        asin = asin_match.group(1).upper() if asin_match else None
        
        if asin:
            # Reconstri a URL no formato mais curto possvel
            new_url = f"https://{parsed.netloc}/dp/{asin}?tag={AMAZON_TAG}" if AMAZON_TAG else f"https://{parsed.netloc}/dp/{asin}"
            print(f"[OK] Link Amazon encurtado via ASIN ({asin}): {new_url}")
            return new_url

        # Fallback caso no ache ASIN (mantm limpeza de parmetros)
        params = parse_qs(parsed.query)
        if 'tag' in params: del params['tag']
        params_to_remove = ['linkCode', 'hvadid', 'hvpos', 'hvnetw', 'hvrand', 'hvpone', 'hvptwo', 'hvqmt', 'hvdev', 'hvdvcmdl', 'hvlocint', 'hvlocphy', 'hvtargid', 'psc', 'language', 'gad_source', 'mcid', 'ref']
        for p in params_to_remove:
            if p in params: del params[p]
        
        params['tag'] = [AMAZON_TAG] 
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    
    # AliExpress
    if 'aliexpress.com' in domain or 'aliexpress.us' in domain or 'aliexpress.ru' in domain or 's.click.aliexpress' in domain:
        return await convert_aliexpress_to_affiliate(url)
    
    # Shopee
    if 'shopee.com.br' in domain or 'shopee.com' in domain:
        return await convert_shopee_to_affiliate(url)
        
    # Futuramente: Magalu...
    
    return clean_tracking_params(url)
