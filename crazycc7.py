import requests
import threading
import time
import random
import sys
import json
import logging
from colorama import Fore, Style, init
import configparser
from typing import Dict, List, Optional
from urllib.parse import urlparse
import re

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('crazycc7.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
CONFIG_DEFAULTS = {
    'Settings': {
        'accounts_file': 'accounts.txt',
        'proxies_file': 'proxies.txt',
        'max_threads': '10',
        'request_timeout': '15',
        'delay_between_requests': '1.0'
    }
}

class CrazyCC7:
    def __init__(self, config_file: str = 'config.ini'):
        self.config = self._load_config(config_file)
        self.accounts_file = self.config['Settings']['accounts_file']
        self.proxies_file = self.config['Settings']['proxies_file']
        self.max_threads = int(self.config['Settings']['max_threads'])
        self.timeout = float(self.config['Settings']['request_timeout'])
        self.delay = float(self.config['Settings']['delay_between_requests'])
        self.lock = threading.Lock()
        self.accounts = self._load_accounts()
        self.proxies = self._load_proxies()
        self.session_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": "https://www.instagram.com/"
        }

    def _load_config(self, config_file: str) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        config.read_dict(CONFIG_DEFAULTS)
        try:
            config.read(config_file)
        except Exception as e:
            logger.error(f"Config file error: {e}")
            logger.info("Using default configuration")
        return config

    def _load_accounts(self) -> List[Dict[str, str]]:
        accounts = []
        try:
            with open(self.accounts_file, "r", encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ":" in line and line.count(":") == 1:
                        user, pwd = line.split(":", 1)
                        accounts.append({"username": user.strip(), "password": pwd.strip()})
            if not accounts:
                logger.error(f"No valid accounts found in {self.accounts_file}")
                sys.exit(1)
            logger.info(f"Loaded {len(accounts)} accounts")
            return accounts
        except FileNotFoundError:
            logger.error(f"Accounts file not found: {self.accounts_file}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error reading accounts file: {e}")
            sys.exit(1)

    def _load_proxies(self) -> List[str]:
        proxies = []
        try:
            with open(self.proxies_file, "r", encoding='utf-8') as f:
                proxies = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(proxies)} proxies")
        except FileNotFoundError:
            logger.info("No proxy file found, proceeding without proxies")
        return proxies

    def _get_random_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        return {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    def _get_csrf_token(self, session: requests.Session, proxy: Optional[Dict[str, str]]) -> Optional[str]:
        try:
            resp = session.get("https://www.instagram.com/", proxies=proxy, timeout=self.timeout)
            csrf_token = resp.cookies.get("csrftoken", "")
            if not csrf_token:
                logger.error("Failed to get CSRF token")
                return None
            return csrf_token
        except Exception as e:
            logger.error(f"Error getting CSRF token: {e}")
            return None

    def login(self, session: requests.Session, username: str, password: str, proxy: Optional[Dict[str, str]]) -> bool:
        login_url = "https://www.instagram.com/accounts/login/ajax/"
        headers = self.session_headers.copy()
        
        csrf_token = self._get_csrf_token(session, proxy)
        if not csrf_token:
            return False
        
        headers["X-CSRFToken"] = csrf_token
        data = {
            "username": username,
            "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}",
            "queryParams": "{}",
            "optIntoOneTap": "false"
        }
        
        try:
            resp = session.post(login_url, data=data, headers=headers, proxies=proxy, timeout=self.timeout)
            json_resp = resp.json()
            if json_resp.get("authenticated"):
                logger.info(f"[{username}] Successfully logged in")
                return True
            else:
                message = json_resp.get("message", "Login failed")
                logger.error(f"[{username}] Login failed: {message}")
                return False
        except Exception as e:
            logger.error(f"[{username}] Login error: {e}")
            return False

    def report_profile(self, session: requests.Session, username: str, target_username: str, proxy: Optional[Dict[str, str]]) -> bool:
        report_url = "https://www.instagram.com/api/v1/users/report/"
        headers = self.session_headers.copy()
        headers["X-CSRFToken"] = session.cookies.get("csrftoken", "")
        
        data = {
            "source_name": "profile",
            "frx_context": json.dumps({
                "entry_point": "profile",
                "location": "profile_page",
                "object_type": "user",
                "object_id": target_username
            }),
            "reason_id": "1"  # Generic violation reason
        }
        
        try:
            resp = session.post(report_url, data=data, headers=headers, proxies=proxy, timeout=self.timeout)
            if resp.status_code == 200:
                logger.info(f"[{username}] Successfully reported profile {target_username}")
                return True
            else:
                logger.warning(f"[{username}] Failed to report profile {target_username}, status code: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[{username}] Error reporting profile: {e}")
            return False

    def report_video(self, session: requests.Session, username: str, video_url: str, proxy: Optional[Dict[str, str]]) -> bool:
        report_url = "https://www.instagram.com/api/v1/media/report/"
        headers = self.session_headers.copy()
        headers["X-CSRFToken"] = session.cookies.get("csrftoken", "")
        
        # Extract video ID from URL
        video_id = self._extract_video_id(video_url)
        if not video_id:
            logger.error(f"[{username}] Invalid video URL: {video_url}")
            return False
            
        data = {
            "source_name": "video",
            "frx_context": json.dumps({
                "entry_point": "video",
                "location": "video_page",
                "object_type": "video",
                "object_id": video_id
            }),
            "reason_id": "1"
        }
        
        try:
            resp = session.post(report_url, data=data, headers=headers, proxies=proxy, timeout=self.timeout)
            if resp.status_code == 200:
                logger.info(f"[{username}] Successfully reported video {video_id}")
                return True
            else:
                logger.warning(f"[{username}] Failed to report video, status code: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[{username}] Error reporting video: {e}")
            return False

    def _extract_video_id(self, url: str) -> Optional[str]:
        try:
            pattern = r"(?:/p/|/reel/|/tv/)([A-Za-z0-9_-]+)"
            match = re.search(pattern, url)
            return match.group(1) if match else None
        except Exception:
            return None

    def worker(self, account: Dict[str, str], report_type: int, target: str):
        session = requests.Session()
        proxy = self._get_random_proxy()
        username = account["username"]
        password = account["password"]
        
        if self.login(session, username, password, proxy):
            with self.lock:
                if report_type == 1:
                    self.report_profile(session, username, target, proxy)
                elif report_type == 2:
                    self.report_video(session, username, target, proxy)
            time.sleep(self.delay)

    def run(self):
        logger.info(f"{Fore.CYAN}Starting CrazyCC7 Instagram Reporting Tool{Style.RESET_ALL}")
        logger.info(f"Loaded {len(self.accounts)} accounts and {len(self.proxies)} proxies")

        while True:
            choice = input(f"{Fore.YELLOW}1 - Report Profile\n2 - Report Video\nChoice: {Style.RESET_ALL}")
            if choice in ["1", "2"]:
                report_type = int(choice)
                break
            logger.error("Invalid choice! Please try again.")

        target = input(f"Enter {'profile username' if report_type == 1 else 'video URL'}: ").strip()
        if not target:
            logger.error("Target cannot be empty!")
            sys.exit(1)

        threads = []
        for account in self.accounts:
            if len(threads) >= self.max_threads:
                for t in threads:
                    t.join()
                threads.clear()
                
            t = threading.Thread(target=self.worker, args=(account, report_type, target))
            t.start()
            threads.append(t)
            time.sleep(self.delay)

        for t in threads:
            t.join()

        logger.info(f"{Fore.GREEN}Reporting process completed!{Style.RESET_ALL}")

if __name__ == "__main__":
    tool = CrazyCC7()
    tool.run()
