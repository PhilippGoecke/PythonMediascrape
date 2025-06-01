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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def recursiv_download(session, url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth, max_depth, cookies):
    if current_depth >= max_depth:
        print(f"Reached maximum recursion depth of {max_depth}, stopping.")
        return

    try:
        response = session.get(url, headers=headers, proxies=proxies, verify=verify_tls)
        #print(f"  Response encoding {response.encoding} apparent_encoding {response.apparent_encoding}")
        print(f"  Response Content Encoding '{response.headers.get('Content-Encoding')}'")

        if "cf-chl-bypass" in response.text or "Checking your browser" in response.text or "chk-hdr" in response.text:
            print(f"  Cloudflare challenge detected. Attempting to bypass...")

            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
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
    print(f"  Saving html: {url} -> {filename}")
    with open(html_path, 'wb') as f:
        f.write(response.text.encode('utf-8'))

    cookies = response.cookies
    print("  Cookies: {}".format(cookies))

    soup = BeautifulSoup(response.text, 'html.parser')

    download_images(soup, url, output_dir, headers, proxies, verify_tls)

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
                        recursiv_download(session, resolved_url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth + 1, max_depth, cookies)
                    else:
                        print(f"    Skipping non-whitelist link: {resolved_url} (Depth: {current_depth + 1}/{max_depth})")
                        continue
                else:
                    print(f"Whitelist Error! {url_whitelist}")
            else:
                print(f"DEBUG resolved_url without http: {resolved_url}")
        #else:
        #    print(f"DEBUG link with no href: {link}")

def download_images(soup, url, output_dir, headers, proxies, verify_tls):
    # Find all image tags
    for img in soup.find_all('img'):
        img_url = urljoin(url, img.get('src'))
        if "?" in str(os.path.splitext(img_url)[1][1:]):
            file_ext = str(os.path.splitext(img_url)[1][1:])[:str(os.path.splitext(img_url)[1][1:]).index('?')]
        else:
            file_ext = os.path.splitext(img_url)[1][1:]
        # Extract filename from original URL
        filename_parts = img_url.split('/')
        url_hash = hashlib.sha1(img_url.encode('utf-8')).hexdigest()
        base_name = filename_parts[-1].split(".")[0][:42]
        filename = f'img_{base_name}_{url_hash}.{file_ext}'
        img_path = os.path.join(output_dir, filename)
        if os.path.exists(img_path):
            print(f"  File {filename} already exists, skipping...")
            continue
        print(f"    Downloading image: {img_url} -> {filename}")
        with open(img_path, 'wb') as f:
            if img_url.startswith('data:'):
                # Handle base64 encoded image data
                header, encoded = img_url.split(',', 1)
                f.write(base64.b64decode(encoded))
            else:
                f.write(requests.get(img_url, headers=headers, proxies=proxies, verify=verify_tls).content)

def download_videos(soup, url, output_dir, headers, proxies, verify_tls):
    # Find all video tags
    for video in soup.find_all(['video', 'source']):
        if video.name == 'source':
            video_url = urljoin(url, video.get('src'))
        else:
            video_url = urljoin(url, video.get('src')) or urljoin(url, video.get('poster'))

        file_ext = os.path.splitext(video_url)[1][1:]
        # Extract filename from original URL
        filename_parts = video_url.split('/')
        url_hash = hashlib.sha1(video_url.encode('utf-8')).hexdigest()
        base_name = filename_parts[-1].split(".")[0][:42]
        filename = f'vid_{base_name}_{url_hash}.{file_ext}'
        video_path = os.path.join(output_dir, filename)
        if os.path.exists(video_path):
            print(f"  File {filename} already exists, skipping...")
            continue
        print(f"    Downloading video: {video_url} -> {filename}")
        with open(video_path, 'wb') as f:
            if video_path.startswith('data:'):
                # Handle base64 encoded video data
                header, encoded = video_path.split(',', 1)
                f.write(base64.b64decode(encoded))
            else:
                f.write(requests.get(video_url, headers=headers, proxies=proxies, verify=verify_tls).content)

def download_media(url, output_dir='downloads', url_whitelist=None, verify_tls=True, max_depth=2, current_depth=0, cookies=None):
    # Create Download Folder
    os.makedirs(output_dir, exist_ok=True)

    # Session
    session = requests.Session()

    # Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        #'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        #'Accept-Encoding': 'gzip, deflate, br',
        #'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Encoding': 'gzip',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # Proxy
    proxies = dict(http='socks5://127.0.0.1:9050',
                   https='socks5://127.0.0.1:9050')

    tld_res = get_tld(url, as_object=True)
    domain = ".".join([tld_res.domain, tld_res.tld])

    print(f"Domain: {domain}")
    if url_whitelist and type(url_whitelist) == type([]):
        if domain not in url_whitelist:
            url_whitelist.append(domain)
        print(f"Whitelist: {url_whitelist}")
    else:
        print(f"Whitelist reset of {url_whitelist}")
        url_whitelist = [domain]
        print(f"  new Whitelist {url_whitelist}")

    if cookies:
        session.cookies.update(cookies)

    #sys.setrecursionlimit(1500)

    recursiv_download(session, url, headers, proxies, output_dir, url_whitelist, verify_tls, current_depth, max_depth, cookies)

    print(f"Scraped {len(scraped_urls)} Pages")

#if __name__ == '__main__':
#    target_url = input("Enter the URL to scrape: ")
#    url_whitelist = input("Enter URL url_whitelist to filter by (optional): ")
#    download_media(target_url, url_whitelist=url_whitelist, verify_tls=True, max_depth=2)
