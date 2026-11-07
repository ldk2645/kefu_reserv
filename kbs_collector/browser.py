import logging
import os
import re
from pathlib import Path
from subprocess import DEVNULL

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait

from .policy import CollectorError, DATA, ENTRY


class Browser:
    def __init__(self, browser="chrome", driver_path=None, *, headless=False, profile_name="kbs"):
        if headless:
            raise CollectorError("HEADED_REQUIRED")
        if browser not in {"edge", "chrome"}:
            raise CollectorError("BROWSER_UNSUPPORTED")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",profile_name):
            raise CollectorError("INVALID_PROFILE_NAME")
        self.browser, self.driver_path = browser, driver_path
        self.driver = None
        # Dedicated persistent browser data, never the user's ordinary Chrome/Edge profile.
        self.profile_path = DATA / "browser_profiles" / browser / profile_name

    def create_options(self):
        options = webdriver.EdgeOptions() if self.browser == "edge" else webdriver.ChromeOptions()
        options.add_argument("--user-data-dir=" + str(self.profile_path.resolve()))
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        options.add_argument("--autoplay-policy=user-gesture-required")
        options.add_experimental_option("prefs", {"download.prompt_for_download": True,
            "credentials_enable_service": False, "profile.password_manager_enabled": False,
            "session.restore_on_startup": 1})
        options.page_load_strategy = "eager"
        return options

    def start(self, url=ENTRY):
        if self.driver is not None:
            raise CollectorError("BROWSER_ALREADY_OPEN")
        self.profile_path.mkdir(parents=True,exist_ok=True)
        os.environ["SE_CACHE_PATH"] = str(DATA / "driver_cache")
        os.environ["SE_AVOID_STATS"] = "true"
        logging.getLogger("selenium").setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        options = self.create_options()
        service_class = EdgeService if self.browser == "edge" else ChromeService
        service = service_class(executable_path=str(Path(self.driver_path).resolve()) if self.driver_path else None,
                                log_output=DEVNULL)
        try:
            create = webdriver.Edge if self.browser == "edge" else webdriver.Chrome
            self.driver = create(options=options, service=service)
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(15)
            self.driver.implicitly_wait(0)
            self.driver.get(url)
        except Exception:
            self.close()
            raise CollectorError("BROWSER_START_FAILED") from None
        return self.driver

    def wait_for_manual_login(self, confirmed=False):
        if not confirmed:
            raise CollectorError("MANUAL_LOGIN_REQUIRED")
        # The operator confirms login; no cookies, storage, credentials or network logs read.
        WebDriverWait(self.driver, 20).until(
            lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"})

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        # Chrome/Edge keep their own cookies in profile_path. Never read/export them,
        # delete the directory on close/failure, or copy authentication to another profile.
