"""Manual navigation is deliberate: no guessed selectors, crawling or automatic clicks."""
from pathlib import Path
import time

from selenium.common.exceptions import StaleElementReferenceException, NoSuchFrameException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .policy import CollectorError, source_allowed, safe_url

DOM = Path(__file__).with_name("dom.js").read_text(encoding="utf-8")


class Navigator:
    def __init__(self, driver, *, fixture=False, timeout=15, interval=3):
        self.driver, self.fixture = driver, fixture
        self.timeout, self.interval = timeout, max(3, interval)
        self.last_read = 0
        self.inspected = set()

    def pace(self):
        remaining = self.interval - (time.monotonic() - self.last_read)
        if remaining > 0:
            time.sleep(remaining)
        self.last_read = time.monotonic()

    def guard(self):
        if not source_allowed(self.driver.current_url, fixture=self.fixture):
            raise CollectorError("LOGIN_OR_SCOPE_REQUIRED")
        if self.driver.execute_script(DOM, "guard", ""):
            raise CollectorError("ACCESS_RESTRICTED")

    def switch_frame(self, path):
        self.driver.switch_to.default_content()
        self.guard()
        for index in path:
            def frame_available(driver):
                frames = driver.find_elements(By.CSS_SELECTOR, "iframe,frame")
                if index < len(frames) and frames[index].is_displayed():
                    driver.switch_to.frame(frames[index])
                    return True
                return False
            WebDriverWait(self.driver, self.timeout).until(frame_available)
            self.guard()

    def inspect(self):
        self.pace()
        frames = []
        top_url = self.driver.current_url
        def visit(path):
            if len(path) > 5 or len(frames) >= 40:
                raise CollectorError("FRAME_LIMIT")
            self.switch_frame(path)
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"})
            result = self.driver.execute_script(DOM, "inspect", "")
            if result.get("overflow"):
                raise CollectorError("DOM_TOO_LARGE")
            frame_url = self.driver.execute_script("return location.href")
            if frame_url != "about:srcdoc" and not safe_url(frame_url, fixture=self.fixture):
                raise CollectorError("UNSAFE_FRAME_URL")
            result.update(path=path, frame_url=frame_url)
            frames.append(result)
            self.inspected.add((top_url, tuple(path)))
            visible_indices = [i for i,e in enumerate(self.driver.find_elements(By.CSS_SELECTOR, "iframe,frame")) if e.is_displayed()]
            for index in visible_indices:
                visit(path+[index])
        try:
            visit([])
            if top_url != self.driver.current_url:
                raise CollectorError("PAGE_CHANGED")
            return {"source_url":top_url, "frames":frames}
        finally:
            self.driver.switch_to.default_content()

    def inspect_region(self, frame, selector):
        """Inspect an already observed body selector on a large detail page."""
        self.pace()
        top_url = self.driver.current_url
        try:
            self.switch_frame(frame)
            result = self.driver.execute_script(DOM, 'inspect-region', selector)
            if result.get('error'):
                raise CollectorError(result['error'])
            if result['descendants'] > 20000:
                raise CollectorError('DOM_TOO_LARGE')
            frame_url = self.driver.execute_script('return location.href')
            if frame_url != 'about:srcdoc' and not safe_url(frame_url,fixture=self.fixture):
                raise CollectorError('UNSAFE_FRAME_URL')
            if top_url != self.driver.current_url:
                raise CollectorError('PAGE_CHANGED')
            self.inspected.add((top_url,tuple(frame)))
            return result
        finally:
            self.driver.switch_to.default_content()

    def extract(self, frame, selector):
        self.pace()
        top_url = self.driver.current_url
        if (top_url, tuple(frame)) not in self.inspected:
            raise CollectorError("INSPECT_FIRST")
        if not selector.strip():
            raise CollectorError("SELECT_ROOT")
        try:
            # At most two DOM attempts; no page refreshes or navigation retries.
            for attempt in range(2):
                try:
                    self.switch_frame(frame)
                    last, stable_since = None, time.monotonic()
                    def stable(driver):
                        nonlocal last, stable_since
                        self.guard()
                        value = driver.execute_script(DOM, "extract", selector)
                        if value.get("error"):
                            return False
                        if value != last:
                            last, stable_since = value, time.monotonic()
                            return False
                        return value if time.monotonic() - stable_since >= 1.5 else False
                    result = WebDriverWait(self.driver, self.timeout, poll_frequency=.5).until(stable)
                    if self.driver.current_url != top_url:
                        raise CollectorError("PAGE_CHANGED")
                    if result["frame_url"] == "about:srcdoc":
                        result["frame_url"] = top_url
                    if not safe_url(result["frame_url"], fixture=self.fixture):
                        raise CollectorError("UNSAFE_FRAME_URL")
                    original_count = len(result["links"])
                    result["links"] = [link for link in result["links"] if safe_url(link["url"],fixture=self.fixture)]
                    result["withheld_links"] = original_count - len(result["links"])
                    result.update(source_url=top_url, frame_path=frame, root_selector=selector)
                    return result
                except (StaleElementReferenceException, NoSuchFrameException):
                    if attempt:
                        raise CollectorError("FRAME_CHANGED") from None
            raise CollectorError("FRAME_CHANGED")
        except TimeoutException:
            raise CollectorError("LOAD_TIMEOUT") from None
        finally:
            self.driver.switch_to.default_content()

    def select_tab(self, index):
        handles = self.driver.window_handles
        if not 0 <= index < len(handles):
            raise CollectorError("TAB_MISSING")
        self.driver.switch_to.window(handles[index])
        self.inspected.clear()

    def scroll(self, frame, selector):
        self.pace()
        try:
            self.switch_frame(frame)
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            self.driver.execute_script("arguments[0].scrollBy(0, Math.max(200, arguments[0].clientHeight * .8))", element)
        finally:
            self.driver.switch_to.default_content()
