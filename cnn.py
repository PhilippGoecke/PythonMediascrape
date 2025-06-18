exec(compile(open("dl.py", "rb").read(), "dl.py", 'exec'))

whitelist = ['cnn.com']

download_folder = 'download_cnn'

base_site = 'https://www.cnn.com/'

download_media(base_site, output_dir=download_folder, url_whitelist=whitelist, max_depth=1)
