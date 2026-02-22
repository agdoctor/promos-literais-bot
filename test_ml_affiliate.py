import asyncio
from affiliate import convert_to_affiliate
from links import expand_url

async def test_conversion():
    ml_link = "https://mercadolivre.com/sec/1zkWkAe"
    
    print(f"--- TESTANDO CONVERSÃO MERCADO LIVRE ---")
    print(f"Original curto: {ml_link}")
    
    # 1. Expandir
    expanded = await expand_url(ml_link)
    print(f"Expandido: {expanded}")
    
    # 2. Converter
    converted = await convert_to_affiliate(expanded)
    
    print(f"Convertida (Afiliado): {converted}")
    
    if converted != expanded and converted != ml_link:
        print("✅ SUCESSO: O link parece ter sido convertido pelo ML!")
    else:
        print("❌ FALHA: O link não foi alterado.")

if __name__ == "__main__":
    asyncio.run(test_conversion())
