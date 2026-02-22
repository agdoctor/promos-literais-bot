import asyncio
from google import genai
import os
from dotenv import load_dotenv

async def test_diag():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY não encontrada no .env")
        return
        
    client = genai.Client(api_key=api_key)
    
    print("📡 Listando todos os modelos disponíveis...")
    try:
        available_models = []
        for model in client.models.list():
            available_models.append(model.name)
            print(f"- {model.name}")
        
        # Tenta os mais prováveis da lista
        for model_name in available_models:
            if "flash" in model_name.lower() or "pro" in model_name.lower():
                try:
                    print(f"\n📡 Testando geração com '{model_name}'...")
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents="Olá"
                    )
                    print(f"✅ Sucesso com {model_name}!")
                    return
                except Exception as e:
                    print(f"❌ Falha com {model_name}: {e}")
    except Exception as e:
        print(f"❌ Erro ao listar modelos: {e}")

if __name__ == "__main__":
    asyncio.run(test_diag())
