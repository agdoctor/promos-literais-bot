import re
import httpx
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

async def expand_url(short_url: str) -> str:
    """
    Função assíncrona que acessa a URL curta e retorna a URL de destino final (após os redirecionamentos).
    """
    try:
        # Usamos follow_redirects=True para acompanhar toda a cadeia até o link final da loja
        # O User-Agent previne que bloqueios automáticos do Mercado Livre ou Amazon rejeitem a conexão
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            response = await client.get(short_url)
            # A URL final
            return str(response.url)
    except Exception as e:
        print(f"Erro ao expandir URL {short_url}: {e}")
        return short_url

def extract_urls(text: str) -> list[str]:
    """
    Encontra e retorna todas as URLs de um texto usando Expressões Regulares (Regex).
    Pega links com ou sem https:// (ex: mercadolivre.com/sec/123).
    """
    # Regex melhorada para pegar domínios conhecidos mesmo sem https
    url_pattern = re.compile(r'(https?://\S+|www\.\S+|mercadolivre\.com\S+|amzn\.to\S+|amzlink\.to\S+|amz\.run\S+|shopee\.com\.br\S+|is\.gd\S+|bit\.ly\S+|tinyurl\.com\S+|cutt\.ly\S+)')
    urls = url_pattern.findall(text)
    
    # Normalizar adicionando https:// se faltar
    normalized_urls = []
    for u in urls:
        if not u.startswith('http'):
            normalized_urls.append('https://' + u)
        else:
            normalized_urls.append(u)
            
    return normalized_urls

# Lista de domínios proibidos (concorrentes, sites de redirecionamento de terceiros)
DOMAIN_BLACKLIST = [
    "nerdofertas.com",
    "t.me", # Evita links para outros canais de telegram que não sejam o oficial
    "chat.whatsapp.com",
    "grupos.link"
]

import affiliate

async def process_and_replace_links(text: str, extra_link: str = None) -> tuple[str, dict]:
    """
    Localiza URLs no texto, as expande, tenta converter em link de afiliado,
    e substitui no texto original por placeholders [LINK_0], [LINK_1] etc.
    Retorna o texto com placeholders e um dicionário mapeando o placeholder para a URL final convertida.
    """
    urls = extract_urls(text)
    if extra_link:
        urls.append(extra_link)
    
    # Dicionário que mapeará o placeholder para a URL convertida final
    placeholder_map = {}
    clean_text = text
    
    # Para evitar substituição parcial (ex: amzn.to/1 e amzn.to/12), vamos usar dict de originais temporário
    unique_urls = list(dict.fromkeys(urls))  # Remove duplicatas mantendo a ordem
    
    for i, original_url in enumerate(unique_urls):
        placeholder = f"[LINK_{i}]"
        clean_text = clean_text.replace(original_url, placeholder)
        
        try:
            # Filtro rápido antes de carregar a URL
            if any(domain in original_url.lower() for domain in DOMAIN_BLACKLIST):
                print(f"🚫 Link bloqueado (Blacklist): {original_url}")
                placeholder_map[placeholder] = None
                continue

            print(f"Processando URL: {original_url}")
            
            # 1. Expandir URL caso seja encurtada (ex: amzn.to)
            expanded_url = await expand_url(original_url)
            
            # Filtro após expandir (previne encurtadores que apontam para concorrentes)
            if any(domain in expanded_url.lower() for domain in DOMAIN_BLACKLIST):
                print(f"🚫 Link expandido bloqueado (Blacklist): {expanded_url}")
                placeholder_map[placeholder] = None
                continue

            print(f"URL Expandida: {expanded_url}")
            
            # 2. Converter para link de afiliado usando o módulo centralizado
            converted_url = await affiliate.convert_to_affiliate(expanded_url)
            placeholder_map[placeholder] = converted_url
            
        except Exception as e:
            print(f"Erro ao processar URL individual {original_url}: {e}")
            placeholder_map[placeholder] = original_url
        
    return clean_text.strip(), placeholder_map
