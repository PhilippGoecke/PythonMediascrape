import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tld import get_tld
import hashlib
import base64
scraped_urls = set()
import sys
print(f"Recursion Limit: {sys.getrecursionlimit()}")
import subprocess
import re
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from stem import Signal
from stem.control import Controller

def switchIP():
    with Controller.from_port(port=9051) as controller:
        controller.authenticate()
        controller.signal(Signal.NEWNYM)

def recursiv_download(session, url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth, max_depth, cookies, headless=True, extra_match=None):
    if current_depth >= max_depth:
        print(f"Reached maximum recursion depth of {max_depth}, stopping.")
        return

    try:
        response = session.get(url, headers=headers, proxies=proxies, verify=verify_tls)
        print(f"  Response Content Encoding '{response.headers.get('Content-Encoding')}'")

        if "cf-chl-bypass" in response.text or "Checking your browser" in response.text or "chk-hdr" in response.text or "challenge-error-text" in response.text:
            print(f"  Cloudflare challenge detected. Attempting to bypass...")

            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='chrome_user_data_')}")
            if proxies and 'http' in proxies:
                chrome_options.add_argument(f"--proxy-server={proxies['http']}")

            chromium_version = re.search(r'(\d+\.\d+\.\d+\.\d+)', subprocess.run(['chromium', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout).group(1)
            print(f"    Chromium Version {chromium_version}")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager(driver_version=chromium_version).install()), options=chrome_options)
            print(f"    ChromeDriver Version {driver.capabilities.get('chrome', {}).get('chromedriverVersion', 'Unknown')}")
            driver.get(url)
            print("  Waiting for Cloudflare challenge to complete...")
            #input("Press Enter to continue ...")
            driver.implicitly_wait(30)
            response_text = driver.page_source
            driver.quit()

            response = type('Response', (object,), {'text': response_text, 'content': response_text.encode('utf-8'), 'cookies': session.cookies})
    except Exception as e:
        print(f"Error during request: {e}")
        return
    print(f"Response {response}")

    url_hash = hashlib.sha1(url.encode('utf-8')).hexdigest()
    filename = f'page_{url_hash}.html'
    html_path = os.path.join(output_dir, filename)
    content_type = response.headers.get('Content-Type', '') if hasattr(response, 'headers') and response.headers else ''
    # Try to determine if content is HTML or contains HTML tags, even if Content-Type is not set correctly
    is_html = False
    if 'text/html' in content_type:
        is_html = True
    else:
        # Heuristic: check if response.text contains <html or <!DOCTYPE html
        try:
            text_sample = response.text[:2048].lower()
            if '<html' in text_sample or '<!doctype html' in text_sample:
                is_html = True
        except Exception:
            pass

    if is_html:
        print(f"  Saving html: {url} -> {filename}")
        with open(html_path, 'wb') as f:
            f.write(response.text.encode('utf-8'))
    else:
        # Save non-HTML content with appropriate extension
        ext = ''
        if 'application/pdf' in content_type:
            ext = '.pdf'
        elif 'image/' in content_type:
            subtype = content_type.split('/')[1].split(';')[0]
            if subtype == 'svg+xml':
                ext = '.svg'
            else:
                ext = '.' + subtype
        elif 'video/' in content_type:
            ext = '.' + content_type.split('/')[1].split(';')[0]
        elif 'audio/' in content_type:
            ext = '.' + content_type.split('/')[1].split(';')[0]
        elif 'font/' in content_type:
            ext = '.' + content_type.split('/')[1]
        elif 'application/json' in content_type:
            ext = '.json'
        elif 'application/javascript' in content_type or 'text/javascript' in content_type:
            ext = '.js'
        elif 'text/css' in content_type:
            ext = '.css'
        elif 'text/xml' in content_type or 'application/xml' in content_type:
            ext = '.xml'
        elif 'application/zip' in content_type:
            ext = '.zip'
        elif 'application/x-font-woff' in content_type:
            ext = '.woff'
        else:
            ext = '.bin'
        non_html_path = os.path.join(output_dir, f'file_{url_hash}{ext}')
        print(f"  Saving non-HTML content: {url} -> {non_html_path}")
        with open(non_html_path, 'wb') as f:
            f.write(response.content)

    cookies = response.cookies
    print("  Cookies: {}".format(cookies))

    # Only parse with BeautifulSoup if content type is HTML
    soup = None
    if is_html or content_type == '':
        soup = BeautifulSoup(response.text, 'html.parser')
    else:
        print("  Skipping BeautifulSoup parsing: content is not HTML.")
        return

    download_images(soup, url, output_dir, headers, proxies, verify_tls, extra_match)

    download_videos(soup, url, output_dir, headers, proxies, verify_tls)

    # Find all links and recurse
    links = soup.find_all('a')

    if len(links) == 0:
        print(f"    scrape found no links!")
    else:
        print(f"    found {len(links)} links")

    for link in links:
        href = link.get('href')
        if href:
            if href.startswith('#'):
                #print(f"DEBUG skip anchor tag: '{href}'")
                continue
            if 'javascript:' in href:
                #print(f"DEBUG skip javascript href: '{href}'")
                continue
            if 'data:' in href:
                print(f"DEBUG skip data href: '{href}'")
                continue
            if href == '':
                #print(f"DEBUG skip empty href: '{href}'")
                continue

            # Resolve relative URLs to absolute URLs
            resolved_url = urljoin(url, href)
            #print(f"DEBUG href: '{href}' -> '{resolved_url}'")

            if resolved_url in scraped_urls:
                print(f"    Skipping already scraped URL: {resolved_url}")
                continue
            scraped_urls.add(resolved_url)

            if resolved_url.startswith('http'):
                if url_whitelist and type(url_whitelist) == type([]):
                    # Check if any keyword is in the resolved URL
                    if any(keyword in resolved_url for keyword in url_whitelist):
                        print(f"  Found link: {resolved_url} (Depth: {current_depth + 1}/{max_depth})")
                        recursiv_download(session, resolved_url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth + 1, max_depth, cookies, headless, extra_match)
                    else:
                        print(f"    Skipping non-whitelist link: {resolved_url} (Depth: {current_depth + 1}/{max_depth})")
                        continue
                else:
                    print(f"Whitelist Error! {url_whitelist}")
            else:
                print(f"DEBUG resolved_url without http: {resolved_url}")
        #else:
        #    print(f"DEBUG link with no href: {link}")

def download_media_file(media_url, output_dir, prefix, headers, proxies, verify_tls):
    # Determine file extension
    if "?" in str(os.path.splitext(media_url)[1][1:]):
        file_ext = str(os.path.splitext(media_url)[1][1:])[:str(os.path.splitext(media_url)[1][1:]).index('?')]
    else:
        file_ext = os.path.splitext(media_url)[1][1:]
        if not file_ext:
            file_ext = 'dat'

    # Extract filename from original URL
    filename_parts = media_url.split('/')
    url_hash = hashlib.sha1(media_url.encode('utf-8')).hexdigest()
    base_name = filename_parts[-1].split(".")[0][:42]
    filename = f'{prefix}_{base_name}_{url_hash}.{file_ext}'
    file_path = os.path.join(output_dir, filename)

    # Check if file already exists
    if os.path.exists(file_path):
        print(f"  File {filename} already exists, skipping...")
        return
    print(f"    Downloading {prefix}: {media_url} -> {filename}")

    # Download the media file
    try:
        if media_url.startswith('data:'):
            # Handle base64 encoded data
            header, encoded = media_url.split(',', 1)
            data = base64.b64decode(encoded)
            with open(file_path, 'wb') as f:
                f.write(data)
        else:
            # Handle standard URL downloads
            media_response = requests.get(media_url, headers=headers, proxies=proxies, verify=verify_tls, stream=True, timeout=42)
            media_response.raise_for_status()  # Raise an exception for bad status codes
            with open(file_path, 'wb') as f:
                for chunk in media_response.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f"      Error downloading {media_url}: {e}")
        # If the file was created, remove it on failure if empty
        if os.path.exists(file_path) and os.path.getsize(file_path) == 0:
            os.remove(file_path)

# extra_match=('thumb', 'large')
def download_images(soup, url, output_dir, headers, proxies, verify_tls, extra_match=None):
    # Find all image tags
    for img in soup.find_all('img'):
        img_src = img.get('src')
        if not img_src:
            continue
        img_url = urljoin(url, img_src)
        download_media_file(img_url, output_dir, 'img', headers, proxies, verify_tls)
        if extra_match:
            if img_url[-7:].find(extra_match[0]) > 0:
                extra_img_url = img_url[::-1].replace(extra_match[0][::-1], extra_match[1], 1)[::-1]
                print(f"      Found extra match, downloading: {extra_img_url}")
                download_media_file(extra_img_url, output_dir, 'img', headers, proxies, verify_tls)

def download_videos(soup, url, output_dir, headers, proxies, verify_tls):
    # Find all video and source tags
    for video in soup.find_all(['video', 'source']):
        video_src = video.get('src')
        if not video_src and video.name == 'video':
            video_src = video.get('poster')
        if not video_src:
            continue
        video_url = urljoin(url, video_src)
        download_media_file(video_url, output_dir, 'vid', headers, proxies, verify_tls)

def download_media(url, output_dir='downloads', url_whitelist=None, verify_tls=True, max_depth=2, current_depth=0, cookies=None, headless=True, extra_match=None):
    # Create Download Folder
    os.makedirs(output_dir, exist_ok=True)

    # Proxy
    proxies = dict(http='socks5://127.0.0.1:9150',
                   https='socks5://127.0.0.1:9150')

    # Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        #'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Encoding': 'gzip',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # Session
    session = requests.Session()
    session.proxies = proxies
    session.verify = verify_tls
    session.headers.update(headers)

    tld_res = get_tld(url, as_object=True)
    domain = ".".join([tld_res.domain, tld_res.tld])

    print(f"Domain: {domain}")
    if url_whitelist and type(url_whitelist) == type([]):
        #if domain not in url_whitelist:
        #    url_whitelist.append(domain)
        print(f"Whitelist: {url_whitelist}")
    else:
        print(f"Whitelist reset of {url_whitelist}")
        url_whitelist = [domain]
        print(f"  new Whitelist {url_whitelist}")

    if cookies and isinstance(cookies, dict):
        session.cookies.update(cookies)

    #sys.setrecursionlimit(1500)

    recursiv_download(session, url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth, max_depth, cookies, headless, extra_match)

    print(f"Scraped {len(scraped_urls)} Pages")

#if __name__ == '__main__':
#    target_url = input("Enter the URL to scrape: ")
#    url_whitelist_input = input("Enter URL whitelist to filter by (comma-separated, optional): ")
#    url_whitelist = [item.strip() for item in url_whitelist_input.split(',')] if url_whitelist_input else None
#    download_media(target_url, url_whitelist=url_whitelist, verify_tls=True, max_depth=2, headless, extra_match)
