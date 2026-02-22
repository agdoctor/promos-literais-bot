import asyncio
from affiliate import convert_to_affiliate

async def test_amazon_links():
    long_link = "https://www.amazon.com.br/PlayStation-CFI-2014B01X-PlayStation%C2%AE5-Edi%C3%A7%C3%A3o-Digital/dp/B0CQKJN2C6/ref=asc_df_B0CQKJN2C6?mcid=10f10aaa0cbe3d519ab13edcf4cc5528&tag=googleshopp00-20&linkCode=df0&hvadid=709884703642&hvpos=&hvnetw=g&hvrand=2342310973383347775&hvpone=&hvptwo=&hvqmt=&hvdev=c&hvdvcmdl=&hvlocint=&hvlocphy=9198641&hvtargid=pla-2281661471176&psc=1&language=pt_BR&gad_source=1"
    short_link = "https://amzn.to/4tM7g4L"

    print("Testing long link...")
    out_long = await convert_to_affiliate(long_link)
    print(f"Result: {out_long}\n")

    print("Testing short link (which gets expanded in links.py first, so let's simulate that)...")
    from links import expand_url
    expanded = await expand_url(short_link)
    print(f"Expanded: {expanded}")
    out_short = await convert_to_affiliate(expanded)
    print(f"Result: {out_short}\n")

if __name__ == "__main__":
    asyncio.run(test_amazon_links())
