import asyncio

async def test_redirect_literally():
    fb_pixel = "PIXEL_ID"
    fb_token = "TOKEN"
    ga_id = "GA_ID" # Test with GA to see bridge page
    long_url = "https://loja.com/produto"
    
    # Logic from literalmente_bot/web_dashboard.py
    # Optimization: Instant redirect if CAPI is present and GA is absent
    if fb_pixel and fb_token and not ga_id:
        print("OPTIMIZATION: Instant Redirect (HTTPFound)")
        return

    html_bridge = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Carregando oferta...</title>
                
                <!-- Google Analytics -->
                {f'''
                <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
                <script>
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){{dataLayer.push(arguments);}}
                  gtag('js', new Date());
                  gtag('config', '{ga_id}');
                </script>
                ''' if ga_id else ""}

                <!-- Facebook Pixel -->
                {f'''
                <script>
                  !function(f,b,e,v,n,t,s)
                  {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
                  n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
                  if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
                  n.queue=[];t=b.createElement(e);t.async=!0;
                  t.src=v;s=b.getElementsByTagName(e)[0];
                  s.parentNode.insertBefore(t,s)}}(window, document,'script',
                  'https://connect.facebook.net/en_US/fbevents.js');
                  fbq('init', '{fb_pixel}');
                  fbq('track', 'PageView');
                </script>
                <noscript><img height="1" width="1" style="display:none" src="https://www.facebook.com/tr?id={fb_pixel}&ev=PageView&noscript=1"/></noscript>
                ''' if (fb_pixel and not fb_token) else ""}

                <style>
                    body {{ font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #1c0e15; color: white; }}
                    .loader {{ border: 4px solid #f3f3f3; border-top: 4px solid #ff66a3; border-radius: 50%; width: 40px; height: 40px; animation: spin 2s linear infinite; margin-bottom: 20px; }}
                    @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                    .container {{ text-align: center; }}
                </style>
                <meta http-equiv="refresh" content='{"0" if (fb_pixel and fb_token and ga_id) else "2"};url={long_url}'>
            </head>
            <body>
                <div class="container">
                    <div class="loader"></div>
                    <p>Redirecionando para a oferta...</p>
                    <small style="opacity: 0.5">Clique <a href="{long_url}" style="color: #ff66a3">aqui</a> se não for redirecionado.</small>
                </div>
                <script>
                    // Backup redirect via JS
                    setTimeout(function() {{ window.location.href = "{long_url}"; }}, {500 if (fb_pixel and fb_token and ga_id) else 2500});
                </script>
            </body>
            </html>
            """
    with open("literally_output.html", "w", encoding="utf-8") as f:
        f.write(html_bridge)
    print("Bridge Page generated in literally_output.html")

if __name__ == "__main__":
    asyncio.run(test_redirect_literally())
