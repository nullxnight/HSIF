import requests
from bs4 import BeautifulSoup
import time
import os
import json
from requests.exceptions import ConnectionError, Timeout, RequestException
import re
import threading
import logging
from queue import Queue
import shutil


logging.basicConfig(filename='app.log', filemode='a', format='%(name)s - %(levelname)s - %(message)s', level=logging.INFO)


proxy = {
    'http': 'socks5h://localhost:9050',
    'https': 'socks5h://localhost:9050'
}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
session = requests.Session()
session.proxies = proxy

def basic_checks():
    try:
        response = session.get("https://check.torproject.org/api/ip", timeout=10).text
        data = json.loads(response)
        logging.info("Tor is running: %s", data['IsTor'])
        print(f"[+] Is Tor Running: {data['IsTor']}")
    except (ConnectionError, Timeout) as err:
        logging.error("Tor is not running: %s", err)
        print('[+] Is Tor Running: False')
        print('[+] Starting Tor')
        os.system('systemctl start tor')
        time.sleep(4)
        basic_checks()

def hostOnion():
    if os.getuid() != 0:
        print("[!] Run this script with SUDO!...")
        exit()
    else: pass
    title = input("[+] Enter Site Name: ")

    os.system(f"mkdir /var/www/html/{title}")
    with open(f"/var/www/html/{title}/index.html",'a')as file:
        file.write("Site Created!")
    
    #Getting Onion Domain!

    with open(f"/etc/tor/torrc",'a')as file:
        file.write(f"HiddenServiceDir /var/lib/tor/{title}/\n")
        file.write(f"HiddenServicePort 80 127.0.0.1:80\n")
    os.system("systemctl restart tor")
    time.sleep(5)
    with open(f"/var/lib/tor/{title}/hostname",'r')as file:
        siteUrl = file.readline()
        print(f"Site URL: http://{siteUrl}")
        print("[+] Setting Up your New site!...")

    #Creating copy of old config
    shutil.copy("/etc/apache2/sites-available/000-default.conf",'/etc/apache2/sites-available/000-default.conf_old')
    #Apache2 setup
    with open('/etc/apache2/sites-available/000-default.conf','w') as file:
        file.write(f"<VirtualHost *:80>\n\tDocumentRoot /var/www/html/{title}\n</VirtualHost>")
    os.system("systemctl restart apache2")
    time.sleep(3)
    print(f"[+] Index: /var/www/html/{title}/index.html ")
    print("[+] Done")


def extract_monero(source_code):
    monero_pattern = r'\b(?:4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})\b'
    return set(re.findall(monero_pattern, source_code))

def extract_ethereum(source_code):
    ethereum_pattern = r'\b(?:0x)[0-9a-fA-F]{40}\b'
    return set(re.findall(ethereum_pattern, source_code))

def save_data_to_file(data, file_path):
    with open(file_path, 'w') as file:
        for item in data:
            file.write(f"{item}\n")

def deanonym():
    d_url = input('[+] Enter Url: ')
    if not d_url.startswith("http://") and not d_url.startswith("https://"):
        d_url = "http://" + d_url


    folder_name = re.sub(r'http?://', '', d_url).replace('/', '_')
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    try:
        response = session.get(d_url, headers=headers, timeout=10).text
        source_code = response

        if source_code:
            result = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', source_code)
            if result:
                print(f"\n[+] {len(result)} Unique Email Addresses found:- \n")
                save_data_to_file(result, os.path.join(folder_name, 'emails.txt'))
                for i in result:
                    print(i)
                print()

            result = re.findall(r'\b[13][a-km-zA-HJ-NP-Z0-9]{26,33}\b', source_code)
            if result:
                print(f"\n[+] {len(result)} Unique BTC Addresses found:- \n")
                save_data_to_file(result, os.path.join(folder_name, 'btc_addresses.txt'))
                for i in result:
                    print(i)
                print()

            result = extract_monero(source_code)
            if result:
                print(f"\n[+] {len(result)} Unique Monero (XMR) Addresses found:- \n")
                save_data_to_file(result, os.path.join(folder_name, 'monero_addresses.txt'))
                for addr in result:
                    print(addr)
                print()

            result = extract_ethereum(source_code)
            if result:
                print(f"\n[+] {len(result)} Unique Ethereum (ETH) Addresses found:- \n")
                save_data_to_file(result, os.path.join(folder_name, 'ethereum_addresses.txt'))
                for addr in result:
                    print(addr)
                print()

            server_status_url = d_url.rstrip('/') + '/server-status'
            try:
                response = session.get(server_status_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    print(f"\n[+] server-status file found at {server_status_url}")
                    html_path = os.path.join(folder_name, 'server_status.html')
                    with open(html_path, 'w') as file:
                        file.write(response.text)
                    print(f"[+] HTML saved to {html_path}")
                else:
                    print(f"\n[+] server-status file not found at {server_status_url}")
            except ConnectionError:
                print(f"\n[!] Failed to connect to {server_status_url}")
    except (ConnectionError, Timeout) as e:
        logging.error("Failed to connect to URL: %s", e)
        print(f"\n[!] Failed to connect to {d_url}")

def check_status(single_url, queue):
    try:
        response = session.get(single_url, timeout=10)
        status_code = response.status_code
        logging.info("Checked URL %s: Status code %d", single_url, status_code)
        queue.put(f"[+] {single_url} [{status_code}]")
    except (ConnectionError, Timeout):
        logging.error("Failed to connect to URL: %s", single_url)
        queue.put(f"[!] {single_url} [DOWN]")

def status():
    s_input = input("[+] Enter the file path to urls: ")
    print()
    queue = Queue()

    with open(s_input, 'r') as sr:
        urls = sr.readlines()
        urls = [url.strip() for url in urls]

        threads = []
        for url in urls:
            if not url.startswith('http'):
                url = 'http://' + url if url.endswith('.onion') else 'https://' + url
            t = threading.Thread(target=check_status, args=(url, queue))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        while not queue.empty():
            print(queue.get())

def scrape_links(url):
    try:
        response = session.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)
        unique_links = set(link.get('href') for link in links if link.get('href').startswith('http'))

        if unique_links:
            print(f"\n[+] {len(unique_links)} Unique Links found:- \n")
            for link in unique_links:
                print(link)
        else:
            print("\n[+] No links found on the page.")
    except (ConnectionError, Timeout) as e:
        logging.error("Failed to connect to URL: %s", e)
        print(f"\n[!] Failed to connect to {url}")

def main():
    print("""
 █████   █████  █████████  █████ ███████████
░░███   ░░███  ███░░░░░███░░███ ░░███░░░░░░█
 ░███    ░███ ░███    ░░░  ░███  ░███   █ ░ 
 ░███████████ ░░█████████  ░███  ░███████   
 ░███░░░░░███  ░░░░░░░░███ ░███  ░███░░░█   
 ░███    ░███  ███    ░███ ░███  ░███  ░    
 █████   █████░░█████████  █████ █████      
░░░░░   ░░░░░  ░░░░░░░░░  ░░░░░ ░░░░░       

    """)

    print("[+] Available Options:- \n")
    print('1. Onion Sites Grabber\n2. Onion Site Investigation\n3. Site Status Checker\n4. Scrape Links\n5. Host Your Onion Site\n')
    func = int(input("[+] Enter Your Choice: "))
    if func == 1:
        query = input("[+] Enter the Query to Grab Sites: ")
        save_choice = input("[+] Do You want to save output[Y/n]: ")
        url = f'https://ahmia.fi/search/?q={query}'

        try:
            response = session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            soup = soup.find_all('cite')
            k = 0
            if save_choice.lower() != 'n':
                with open(f"{query}.txt", 'a') as d:
                    for i in soup:
                        d.write(i.text + '\n')
                        k += 1
                print(f'[+] Success: {k} Unique URLs were written to {query}.txt')
            else:
                for i in soup:
                    print(i.text)
                    k += 1
            print("\n[+] Number of Unique URLs: ", k)
        except (ConnectionError, Timeout) as e:
            logging.error("Failed to connect to URL: %s", e)
            print(f"\n[!] Failed to connect to {url}")

    elif func == 2:
        deanonym()

    elif func == 3:
        status()

    elif func == 4:
        url = input("[+] Enter the URL to scrape links: ")
        scrape_links(url)
    elif func == 5:
        hostOnion()
    else:
        print("[!] Invalid Option Selected...")
        logging.error("Invalid option selected")
        print("\n Exiting...")
        exit()

if __name__ == "__main__":
    main()
