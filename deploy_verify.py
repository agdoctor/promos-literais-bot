import os
import sys
import httpx
import asyncio
from scraper import fetch_product_metadata
from links import expand_url, process_and_replace_links

async def verify_deployment():
    print("🔍 [VERIFY] Iniciando Diagnóstico de Implantação")
    print("-" * 40)
    
    # 1. Verificar Variáveis de Ambiente
    env_vars = ['BOT_TOKEN', 'GEMINI_API_KEY', 'API_ID', 'API_HASH', 'TARGET_CHANNEL']
    print("📡 Verificando Variáveis de Ambiente:")
    for var in env_vars:
        val = os.getenv(var)
        status = "✅ Configurado" if val else "❌ NÃO ENCONTRADO"
        print(f"  - {var}: {status}")
        
    # 2. Verificar Permissões de Escrita
    print("\n📁 Verificando Permissões de Pasta:")
    try:
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
            print("  - downloads/: ✅ Criada com sucesso")
        else:
            print("  - downloads/: ✅ Já existe")
            
        test_file = "downloads/write_test.txt"
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        print("  - Escrita em downloads/: ✅ Sucesso")
    except Exception as e:
        print(f"  - downloads/: ❌ Erro de permissão: {e}")

    # 3. Testar Scraper (Conectividade Amazon)
    print("\n🌐 Testando Scraper (Amazon):")
    test_url = "https://www.amazon.com.br/dp/B088GH9ST5" # Exemplo: Pequeno Príncipe
    try:
        metadata = await fetch_product_metadata(test_url)
        if metadata.get("title") and "Erro" not in metadata.get("title"):
            print(f"  - Scraper Título: ✅ Sucesso ('{metadata['title'][:30]}...')")
        else:
            print(f"  - Scraper Título: ❌ Falha (Bloqueio ou Erro)")
            
        if metadata.get("local_image_path"):
            print(f"  - Scraper Imagem: ✅ Sucesso ('{metadata['local_image_path']}')")
        else:
            print(f"  - Scraper Imagem: ❌ Falha (IP bloqueado para imagens?)")
    except Exception as e:
        print(f"  - Scraper: ❌ Erro Fatal: {e}")

    # 4. Testar Expansão de Links
    print("\n🔗 Testando Expansão de Links:")
    test_short = "https://amzn.to/3OUMr88"
    try:
        expanded = await expand_url(test_short)
        if "amazon.com.br" in expanded:
            print(f"  - Expansão: ✅ Sucesso")
        else:
            print(f"  - Expansão: ❌ Falha (Retornou: {expanded})")
    except Exception as e:
        print(f"  - Expansão: ❌ Erro: {e}")

    print("-" * 40)
    print("✅ Diagnóstico Concluído.")

if __name__ == "__main__":
    asyncio.run(verify_deployment())
