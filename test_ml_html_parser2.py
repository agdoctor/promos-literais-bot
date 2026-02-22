import asyncio
from bs4 import BeautifulSoup
import re

async def main():
    with open("ml_social_dump.html", "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Tenta pelo seletor de classe indicado pelo bot
    featured_link = soup.select_one("a.poly-component__link--action-link")
    if featured_link and featured_link.get("href"):
        print(f"Encontrado via classe CSS: {featured_link['href']}")
    
    # 2. Tenta por href contendo card-featured
    featured_link_href = soup.find("a", href=re.compile("card-featured"))
    if featured_link_href:
        print(f"Encontrado via href regex: {featured_link_href['href']}")

asyncio.run(main())
