import asyncio
import os
import sys

# Adiciona o diretório atual ao path para importar as funções
sys.path.append(os.getcwd())

async def test_literalmente_bot():
    from affiliate import get_shopee_product_info
    
    url = "https://s.shopee.com.br/7VBEgIyzUE"
    print(f"--- Testando Literalmente Bot (Link Suspeito): {url} ---")
    
    try:
        result = await get_shopee_product_info(url)
        if result:
            print(f"Título: {result.get('title')}")
            print(f"Imagem: {result.get('image')}")
            if result.get('image') and result.get('title') != "opaanlp":
                print("SUCCESS: Descriptive title and image extracted.")
            else:
                print(f"WARNING: Extracted title is '{result.get('title')}'. Image: {result.get('image')}")
        else:
            print("FAILURE: No data returned.")
    except Exception as e:
        print(f"ERROR during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_literalmente_bot())
