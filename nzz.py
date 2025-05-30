exec(compile(open("dl.py", "rb").read(), "dl.py", 'exec'))

whitelist = ['nzz.ch']

download_folder = 'download_nzz'

base_site = 'https://www.nzz.ch/'

download_media(base_site, output_dir=download_folder, url_whitelist=whitelist, verify_tls=True, max_depth=1)
