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

def clean_tracking_params(url: str) -> str:
    """
    Remove parâmetros de rastreamento conhecidos para evitar conflitos e links sujos.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Lista de parâmetros para remover
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
                    # 2. Se não for lista, tentar achar o produto em destaque usual
                    # O produto destacado no topo tem a classe poly-component__link--action-link
                    featured_link = soup.select_one("a.poly-component__link--action-link")
                    if not featured_link:
                        # Fallback via url
                        featured_link = soup.find("a", href=re.compile("card-featured"))
                        
                    if featured_link and featured_link.get("href"):
                        target_product_url = featured_link['href']
                        print(f"✅ Produto extraído da vitrine: {target_product_url}")
                    else:
                        print(f"[ERR] Nao foi possivel encontrar o produto destacado ou lista na vitrine.")
        except Exception as e:
            print(f"[!] Erro ao acessar vitrine social: {e}")

    # Limpar a URL do produto antes de enviar para a API
    clean_url = clean_tracking_params(target_product_url)

    # Se a API falhar, o fallback é passar a URL original inteira (ou limpa) no ref do nosso link social genérico
    fallback_social_url = f"https://www.mercadolivre.com.br/social/drmkt?forceInApp=true&matt_word=drmk&ref={clean_url}"

    try:
        print(f"Convertendo ML via API Stripe: {clean_url}")
        # A API Stripe exige um NOVO cliente httpx para não enviar _csrf cookies das requisições anteriores
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

    
    # Parâmetros obrigatórios da API TopClient AliExpress
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
    # 1. Ordenar parâmetros em ordem alfabética pela chave
    sorted_keys = sorted(params.keys())
    # 2. String = SECRET_KEY + key1 + value1 + key2 + value2 ... + SECRET_KEY
    sign_str = ALI_APP_SECRET
    for k in sorted_keys:
        sign_str += str(k) + str(params[k])
    sign_str += ALI_APP_SECRET
    
    # 3. MD5 hash em Maiúsculo
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
                        print(f"⚠️ Erro ao converter item no AliExpress: {item_info.get('message', 'Desconhecido')}")
                else:
                    print("[!] Modulo promotion_links vazio na resposta.")
                        
            except Exception as parse_err:
                print(f"⚠️ Erro ao analisar resposta do AliExpress: {parse_err}. Retorno bruto: {data}")
                return get_fallback_url(clean_url)

    except Exception as e:
        print(f"[!] Erro ao gerar link de afiliado AliExpress: {e}")
        
    return get_fallback_url(clean_url)

async def shorten_url_tiny(long_url: str) -> str:
    """Encurtador de URL via TinyURL público."""
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
    import hmac
    import hashlib
    import time
    import json
    
    SHOPEE_APP_ID = getattr(config, 'SHOPEE_APP_ID', None)
    SHOPEE_APP_SECRET = getattr(config, 'SHOPEE_APP_SECRET', None)
    SHOPEE_AFFILIATE_ID = getattr(config, 'SHOPEE_AFFILIATE_ID', None)
    
    # 1. Limpar a URL
    clean_url_str = clean_tracking_params(original_url)
    
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        print("[!] Credenciais da API Shopee (AppID/Secret) nao configuradas. Usando fallback Universal Link.")
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
    Busca informações detalhadas do produto (título e imagem) via API oficial.
    Requer SHOPEE_APP_ID e SHOPEE_APP_SECRET.
    """
    import config
    import json
    import time
    import hashlib
    
    app_id = getattr(config, 'SHOPEE_APP_ID', None)
    app_secret = getattr(config, 'SHOPEE_APP_SECRET', None)
    
    if not app_id or not app_secret:
        return None

    # Extrair Item ID da URL expandida ou original
    item_id = None
    # Padrao 1: /product/SHOP_ID/ITEM_ID
    match1 = re.search(r'shopee\.com\.br/product/\d+/(\d+)', url)
    if match1:
        item_id = match1.group(1)
    else:
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

    # Extrair Item ID de varios formatos
    item_id = None
    m = re.search(r'-i\.(\d+)\.(\d+)', working_url)
    if m:
        item_id = m.group(2)
    if not item_id:
        m = re.search(r'shopee\.com\.br/[^?]+/(\d+)/(\d+)', working_url)
        if m:
            item_id = m.group(2)
    if not item_id:
        m = re.search(r'[?&]itemid=(\d+)', working_url, re.IGNORECASE)
        if m:
            item_id = m.group(1)
    if not item_id:
        print(f"[Shopee API] Nao foi possivel extrair item_id da URL: {working_url[:120]}")
        return None
    print(f"[Shopee API] Buscando produto item_id={item_id}")

    api_url = "https://open-api.affiliate.shopee.com.br/graphql"
    
    # Query para buscar detalhes do produto
    # productOfferV2 e ideal porque aceita itemIds e retorna dados de afiliado
    query = """
    query ($itemIds: [Long]!) {
      productOfferV2(itemIds: $itemIds) {
        nodes {
          itemName
          imageUrl
          price
        }
      }
    }
    """
    variables = {"itemIds": [int(item_id)]}
    body = json.dumps({"query": query, "variables": variables}, separators=(',', ':'))
    timestamp = int(time.time())
    
    # Algoritmo Oficial: SHA256(AppId + Timestamp + Body + Secret)
    base_str = f"{app_id}{timestamp}{body}{app_secret}"
    signature = hashlib.sha256(base_str.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Signature={signature}, Timestamp={timestamp}"
    }

    try:
        print(f"Buscando metadados Shopee via API Oficial para item {item_id}...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, headers=headers, content=body)
            if response.status_code == 200:
                data = response.json()
                nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
                if nodes:
                    prod = nodes[0]
                    return {
                        "title": prod.get("itemName"),
                        "image": prod.get("imageUrl")
                    }
            else:
                print(f"[!] Erro API Shopee Info ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"[!] Erro ao buscar info Shopee via API: {e}")
        
    return None

async def convert_to_affiliate(url: str) -> str:
    """
    Identifica a loja e aplica a lógica de conversão correspondente.
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
        from database import get_config as _get_cfg
        AMAZON_TAG = _get_cfg("AMAZON_TAG") or getattr(config, 'AMAZON_TAG', '')
        
        # Tenta extrair o ASIN (10 caracteres alfanuméricos)
        # Padrões comuns: /dp/ASIN, /gp/product/ASIN, /exec/obidos/ASIN
        asin_match = re.search(r'/(?:dp|gp/product|exec/obidos|aw/d)/([A-Z0-9]{10})', url, re.IGNORECASE)
        asin = asin_match.group(1).upper() if asin_match else None
        
        if asin:
            # Reconstrói a URL no formato mais curto possível
            new_url = f"https://{parsed.netloc}/dp/{asin}?tag={AMAZON_TAG}" if AMAZON_TAG else f"https://{parsed.netloc}/dp/{asin}"
            print(f"[OK] Link Amazon encurtado via ASIN ({asin}): {new_url}")
            return new_url

        # Fallback caso não ache ASIN (mantém limpeza de parâmetros)
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
