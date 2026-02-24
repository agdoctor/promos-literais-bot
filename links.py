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
    # Regex melhorada: pega domínios conhecidos mas exclui pontuação final, caracteres HTML e marcas de formatação (* _ ~)
    # Usamos lookbehind negativo para não incluir pontuação no final da URL
    url_pattern = re.compile(r'(?:https?://|www\.)[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|mercadolivre\.com[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|meli\.la[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|amzn\.to[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|amz\.run[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|shopee\.com\.br[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|is\.gd[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|bit\.ly[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|tinyurl\.com[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])|cutt\.ly[^\s!?,;\"\'<>()[\]{}*_~]+(?<![.!?,;])')
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
        # Coloca o link extra (se vindo do scraper manual) no início para ser o [LINK_0]
        urls.insert(0, extra_link)
    
    # Dicionário que mapeará o placeholder para a URL convertida final
    placeholder_map = {}
    clean_text = text
    
    # Para evitar substituição parcial (ex: amzn.to/1 e amzn.to/12), vamos usar dict de originais temporário
    unique_urls = list(dict.fromkeys(urls))  # Remove duplicatas mantendo a ordem
    
    # Contador manual para garantir que os placeholders sejam sequenciais [LINK_0], [LINK_1]...
    # mesmo que a gente pule links internos
    curr_placeholder_idx = 0
    
    for original_url in unique_urls:
        try:
            # Se for um link do nosso próprio canal (usado para cupons), não substituímos por placeholder nem bloqueamos
            if "t.me/promosliterais" in original_url.lower():
                continue

            placeholder = f"[LINK_{curr_placeholder_idx}]"
            curr_placeholder_idx += 1

            # Se chegamos aqui, é um link válido para processar
            # MAS, se ele estiver na blacklist, substituímos pelo placeholder mas marcamos como None para ser removido depois
            if any(domain in original_url.lower() for domain in DOMAIN_BLACKLIST):
                print(f"🚫 Link bloqueado (Blacklist): {original_url}")
                clean_text = clean_text.replace(original_url, placeholder)
                placeholder_map[placeholder] = None
                continue

            # Processamento Normal
            clean_text = clean_text.replace(original_url, placeholder)
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
