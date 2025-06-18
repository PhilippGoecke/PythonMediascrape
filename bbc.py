exec(compile(open("dl.py", "rb").read(), "dl.py", 'exec'))

whitelist = ['bbc.com']

download_folder = 'download_bbc'

base_site = 'https://www.bbc.com/'

download_media(base_site, output_dir=download_folder, url_whitelist=whitelist, verify_tls=True, max_depth=1, headless=False)
