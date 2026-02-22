import asyncio
import os
from dotenv import load_dotenv
from rewriter import gerar_promocao_por_link

async def test():
    load_dotenv()
    print("📡 Testando geração de promoção...")
    titulo = "O Hobbit"
    link = "https://www.amazon.com.br/dp/8551002732"
    preco = "45.90"
    cupom = "-"
    
    try:
        resultado = await gerar_promocao_por_link(titulo, link, preco, cupom)
        print("\n=== RESULTADO DO GEMINI ===")
        print(resultado)
        print("===========================")
        
        if "[LINK_0]" not in resultado:
            print("⚠️ AVISO: [LINK_0] não está no resultado!")
        if "<b>" not in resultado:
            print("⚠️ AVISO: <b> não está no resultado!")
            
    except Exception as e:
        print(f"❌ Erro no teste: {e}")

if __name__ == "__main__":
    asyncio.run(test())
