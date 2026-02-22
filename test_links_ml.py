import asyncio
from links import process_and_replace_links

async def test():
    text = "CUPOM ESGOTANDO! 🔥\nUse o Cupom: <code>MERCADOMELI</code>\n\nhttps://mercadolivre.com/sec/1zkWkAe"
    clean_text, final_links = await process_and_replace_links(text)
    
    print("=== TEXTO FINAL ===")
    print(clean_text)
    print("=== LINKS FINAIS ===")
    for link in final_links:
        print(link)

if __name__ == "__main__":
    asyncio.run(test())
