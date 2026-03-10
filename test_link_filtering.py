import asyncio
import os
import sys

# Adicionar o diretório atual ao sys.path para importar os módulos locais
sys.path.append(os.getcwd())

from links import process_and_replace_links, extract_urls
from affiliate import is_store_link

async def test_filtering():
    print("--- [TEST] Iniciando Testes de Filtragem de Links ---")
    
    # Mocking external calls
    import affiliate
    import database
    
    # Salvar originais
    original_convert = affiliate.convert_to_affiliate
    original_get_config = database.get_config
    
    # Mock coverter to just return the same URL (no real network)
    async def mock_convert(url):
        return url
    affiliate.convert_to_affiliate = mock_convert
    
    # Mock database config
    def mock_get_config(key):
        return ""
    database.get_config = mock_get_config

    # Caso 1: Post com diversos links (Loja, Rede Social, Concorrente)
    text = """
🚨 NOVO CUPOM NA AMAZON

R$100 OFF em compras acima de R$99 
🏷 CUPOMZAO

➡️ https://amzn.to/4rLTnlH (LOJA - DEVE MANTER)
➡️ https://amzn.to/4rLTnlH (LOJA - DEVE MANTER)

⚠️ exclusivo no app

#parceria 
https://bit.ly/comprawpp (CONCORRENTE/WHATSAPP - DEVE REMOVER)
https://t.me/compretudocomdesconto (TELEGRAM - DEVE REMOVER)
"""
    
    print("\n1. Testando processamento de post misto...")
    
    urls_extraidas = extract_urls(text)
    print(f"URLs extraídas: {urls_extraidas}")
    
    # Verificação básica de extração
    assert any("amzn.to" in u for u in urls_extraidas)
    assert any("bit.ly" in u for u in urls_extraidas)
    
    clean_text, p_map = await process_and_replace_links(text)
    
    print(f"Texto Processado:\n{clean_text}")
    print(f"Mapa de Placeholders: {p_map}")
    
    # Verificar se links da Amazon foram mantidos (pelo menos no placeholder)
    amazon_placeholders = [p for p, url in p_map.items() if url and ("amazon" in url or "amzn.to" in url)]
    print(f"Links Amazon encontrados no mapa: {len(amazon_placeholders)}")
    assert len(amazon_placeholders) > 0, "Deveria ter mantido links da Amazon"
    
    # Verificar se links de Telegram/Bitly concorrente foram marcados como None ou removidos
    # bit.ly e t.me estão na blacklist
    blocked_placeholders = [p for p, url in p_map.items() if url is None]
    print(f"Links Bloqueados (None no mapa): {len(blocked_placeholders)}")
    assert len(blocked_placeholders) >= 2, "Deveria ter bloqueado os links da blacklist (bit.ly e t.me)"
    
    # Caso 2: Testar is_store_link individualmente
    print("\n2. Testando is_store_link...")
    assert is_store_link("https://www.amazon.com.br/dp/123") == True
    assert is_store_link("https://shopee.com.br/product/1/2") == True
    assert is_store_link("https://www.mercadolivre.com.br/p/MLB123") == True
    assert is_store_link("https://chat.whatsapp.com/ABC") == False
    assert is_store_link("https://t.me/canal") == False
    assert is_store_link("https://instagram.com/perfil") == False
    print("✅ is_store_link validado!")

    # Caso 3: Verificar se o monitor.py filtraria corretamente (simulação da lógica)
    print("\n3. Simulando lógica do monitor.py...")
    social_domains = ["youtube.com", "youtu.be", "t.me", "chat.whatsapp.com", "instagram.com", "facebook.com"]
    
    valid_buy_links = {}
    for p, url in p_map.items():
        if not url: continue
        if any(social in url.lower() for social in social_domains): continue
        if is_store_link(url):
            valid_buy_links[p] = url
            
    print(f"Links de compra válidos: {valid_buy_links}")
    for url in valid_buy_links.values():
        # Validamos que apenas lojas sobraram
        assert is_store_link(url), f"Link {url} não deveria estar nos links de compra válidos"
    
    # Restaurar originais
    affiliate.convert_to_affiliate = original_convert
    database.get_config = original_get_config
    
    print("\n✅ Todos os testes de filtragem passaram!")

if __name__ == "__main__":
    asyncio.run(test_filtering())
