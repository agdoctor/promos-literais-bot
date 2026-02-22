import re

with open("ml_social_dump.html", "r", encoding="utf-8") as f:
    html = f.read()

# Procura qualquer URL que contenha MLB seguido de números
# Ex: https://produto.mercadolivre.com.br/MLB-27581501... ou https://www.mercadolivre.com.br/apple-iphone.../p/MLB...
urls = re.findall(r'https?://[^\s\'"<>]+MLB[^\s\'"<>]+', html)

# Limpa e filtra
unique_urls = list(set(urls))
for u in unique_urls:
    # Ignora URLs de CSS/assets se existirem
    if "http" in u:
        print(f"URL: {u}")

