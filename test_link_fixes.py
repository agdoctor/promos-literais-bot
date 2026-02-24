import asyncio
import re
from links import extract_urls, process_and_replace_links

async def test_fixes():
    print("--- Testando Extração de URLs (Literalmente) ---")
    text_with_html = '<a href="https://t.me/promosliterais"><code>CUPOM</code></a>'
    urls = extract_urls(text_with_html)
    print(f"URLs extraídas de HTML: {urls}")
    assert "https://t.me/promosliterais" in urls
    # Verifica se não pegou as aspas ou tags
    for u in urls:
        assert '"' not in u
        assert ">" not in u
        assert "<" not in u

    text_with_punc = 'Olha esse link: https://amzn.to/xxxx! e esse https://meli.la/yyyy. Legal né?'
    urls = extract_urls(text_with_punc)
    print(f"URLs extraídas com pontuação: {urls}")
    assert "https://amzn.to/xxxx" in urls
    assert "https://meli.la/yyyy" in urls
    assert "https://amzn.to/xxxx!" not in urls

    print("\n--- Testando Processamento e Placeholders (Literalmente) ---")
    text = 'Compre aqui: https://amzn.to/orig e use o cupom em <a href="https://t.me/promosliterais">link</a>'
    extra = "https://example.com/promo"
    
    clean_text, p_map = await process_and_replace_links(text, extra)
    
    print(f"Texto Limpo: {clean_text}")
    print(f"Mapa de Placeholders: {p_map}")
    
    # [LINK_0] deve ser o 'extra'
    assert p_map.get("[LINK_0]") == "https://example.com/promo"
    
    # O link do canal oficial NÃO deve ter sido substituído por placeholder
    assert "https://t.me/promosliterais" in clean_text
    assert "[LINK_1]" in clean_text
    
    print("\n✅ Todos os testes de link do Literalmente passaram!")

if __name__ == "__main__":
    asyncio.run(test_fixes())
