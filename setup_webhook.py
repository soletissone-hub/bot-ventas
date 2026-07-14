import urllib.request
TOK='8723725863:AAHKlRoHkk7fqV0TlMDpLhazXVT6ExHpjxM'
URL='https://soletissone.pythonanywhere.com'
proxy=urllib.request.ProxyHandler({'https':'http://proxy.server:3128','http':'http://proxy.server:3128'})
opener=urllib.request.build_opener(proxy)
url=f'https://api.telegram.org/bot{TOK}/setWebhook?url={URL}/{TOK}'
print(opener.open(url).read().decode())
