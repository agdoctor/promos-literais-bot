import asyncio
from links import extract_urls, process_and_replace_links

async def test_shortener():
    text = "Aqui está um link curto is.gd/QWXZ e um com protocolo https://bit.ly/ASDF"
    
    print("Testing extraction...")
    urls = extract_urls(text)
    print(f"Extracted URLs: {urls}\n")
    
if __name__ == "__main__":
    asyncio.run(test_shortener())
