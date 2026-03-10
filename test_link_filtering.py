import asyncio
import os
import sys

# Adicionar o diretório atual ao sys.path para importar os módulos locais
sys.path.append(os.getcwd())

from links import process_and_replace_links, extract_urls, is_store_link

async def test_filtering():
    print("--- [TEST] Iniciando Testes de Filtragem por WHITELIST ---")
    
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

    # Caso 1: Mix de links permitidos e proibidos
    text = """
🚨 OFERTA IMPERDÍVEL

➡️ https://amzn.to/4rLTnlH (LOJA - PERMITIDO)
➡️ https://www.mercadolivre.com.br/p/MLB123 (LOJA - PERMITIDO)

⚠️ Cupom exclusivo:
🏷 CUPOMZAO (t.me/promosliterais - PERMITIDO INTERNO)

Redes sociais (DEVE REMOVER):
- https://instagram.com/perfil
- https://bit.ly/concorrente (Redireciona para WhatsApp - DEVE REMOVER)
- https://fala-luiz.com.br (Blacklist Concorrente - DEVE REMOVER)
"""
    
    print("\n1. Testando processamento com Whitelist...")
    
    # Simular expansão para o bit.ly
    from links import expand_url
    original_expand = expand_url
    
    async def mock_expand(url):
        if "bit.ly" in url:
            return "https://chat.whatsapp.com/concorrente"
        return url
    
    # Aplicar mock de expansão (Monkey patching local import if possible or just rely on the logic)
    import links
    links.expand_url = mock_expand
    
    clean_text, p_map = await process_and_replace_links(text)
    
    print(f"Texto Processado:\n{clean_text}")
    print(f"Mapa de Placeholders: {p_map}")
    
    # Verificar permitidos
    allowed = [url for url in p_map.values() if url is not None]
    print(f"Links permitidos: {allowed}")
    
    assert any("amazon" in str(u) or "amzn.to" in str(u) for u in allowed), "Amazon deveria constar"
    assert any("mercadolivre" in str(u) for u in allowed), "Mercado Livre deveria constar"
    
    # Verificar bloqueados
    blocked_count = list(p_map.values()).count(None)
    print(f"Links bloqueados (None no mapa): {blocked_count}")
    assert blocked_count >= 3, "Deveria ter bloqueado Instagram, bit.ly(WhatsApp) e fala-luiz"

    # Caso 2: Testar is_store_link individualmente
    print("\n2. Testando is_store_link individualmente...")
    assert is_store_link("https://www.amazon.com.br/dp/123") == True
    assert is_store_link("https://shopee.com.br/product/1/2") == True
    assert is_store_link("https://mglu.io/xyz") == True
    assert is_store_link("https://facebook.com/xyz") == False
    assert is_store_link("https://google.com") == False
    print("✅ is_store_link validado!")

    # Restaurar originais
    affiliate.convert_to_affiliate = original_convert
    database.get_config = original_get_config
    links.expand_url = original_expand
    
    print("\n✅ Todos os testes de WHITELIST passaram!")

if __name__ == "__main__":
    asyncio.run(test_filtering())
