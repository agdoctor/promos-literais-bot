import asyncio
from scraper import fetch_product_metadata
from links import process_and_replace_links
from rewriter import gerar_promocao_por_link
import os

async def test_link():
    link = "https://www.amazon.com.br/empregada-Bem-vinda-%C3%A0-fam%C3%ADlia/dp/6555655062/ref=asc_df_6555655062?mcid=12e150bb6bd73e0391061e6d18e033eb&tag=googleshopp00-20&linkCode=df0&hvadid=709857900177&hvpos=&hvnetw=g&hvrand=9449458283127400367&hvpone=&hvptwo=&hvqmt=&hvdev=c&hvdvcmdl=&hvlocint=&hvlocphy=9100815&hvtargid=pla-2200010596506&psc=1&language=pt_BR&gad_source=1"
    
    print(f"--- Testando Scraper ---")
    metadata = await fetch_product_metadata(link)
    print(f"Metadata: {metadata}")
    
    if metadata['title']:
        print(f"\n--- Testando Geração de Copy (IA) ---")
        # Simulando dados que viriam do fluxo manual
        titulo = metadata['title']
        preco = "34.90"
        cupom = "-"
        
        texto_base = await gerar_promocao_por_link(titulo, link, preco, cupom)
        print(f"Texto Base IA:\n{texto_base}")
        
        print(f"\n--- Testando Processamento de Links ---")
        texto_final, placeholder_map = await process_and_replace_links(texto_base, link)
        print(f"Texto com Placeholders:\n{texto_final}")
        print(f"Placeholder Map: {placeholder_map}")
        
        # Remontando (como no admin.py)
        for ph, url in placeholder_map.items():
            if url:
                texto_final = texto_final.replace(ph, f"<a href='{url}'>Link</a>")
        
        print(f"\n--- Resultado Final ---")
        print(texto_final)
    else:
        print("❌ Scraper falhou em obter o título.")

if __name__ == "__main__":
    asyncio.run(test_link())
