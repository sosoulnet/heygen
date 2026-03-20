#!/usr/bin/env python3
"""
HeyGen Video Creator — Selenium Browser Automation

Reads text files from a folder and creates HeyGen videos by automating
the web UI at app.heygen.com. No API key needed — uses browser login.

Usage:
    python heygen_video_creator.py /path/to/text/files

The script will:
1. Open a browser and let you log in to HeyGen
2. For each .txt file, create a new video in the Studio
3. Select portrait mode, no avatar, paste the script text
4. Submit for generation
5. Wait for completion and download to a "downloads" subfolder

Requirements:
    pip install -r requirements.txt

Environment variables (optional, in .env):
    HEYGEN_EMAIL    - Auto-fill login email
    HEYGEN_PASSWORD - Auto-fill login password
    HEYGEN_HEADLESS - Set to "1" for headless mode (default: visible browser)
"""

import argparse
import glob
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

HEYGEN_URL = "https://app.heygen.com"
MAX_WAIT = 60  # seconds to wait for elements
VIDEO_WAIT = 600  # seconds to wait for video generation


def create_driver(headless=False, download_dir=None):
    """Create and configure a Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if download_dir:
        prefs = {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }
        options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def wait_and_click(driver, by, value, timeout=MAX_WAIT, description="element"):
    """Wait for an element to be clickable and click it."""
    print(f"    Waiting for {description}...")
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )
    time.sleep(0.5)
    el.click()
    return el


def wait_for_element(driver, by, value, timeout=MAX_WAIT, description="element"):
    """Wait for an element to be present."""
    print(f"    Waiting for {description}...")
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def wait_for_visible(driver, by, value, timeout=MAX_WAIT, description="element"):
    """Wait for an element to be visible."""
    print(f"    Waiting for {description}...")
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def login(driver, email=None, password=None):
    """Navigate to HeyGen and ensure the user is logged in.

    First checks if the user is already logged in. If a login page appears,
    auto-fills credentials (if provided) or waits 30 seconds for the user
    to log in manually.
    """
    driver.get(HEYGEN_URL)
    print("  Navigated to HeyGen...")
    time.sleep(3)

    # Check if already logged in (no login/signup in the URL)
    if "/login" not in driver.current_url and "/signup" not in driver.current_url:
        print("  Already logged in!")
        return

    print("  Login page detected.")

    if not email:
        email = os.environ.get("HEYGEN_EMAIL")
    if not password:
        password = os.environ.get("HEYGEN_PASSWORD")

    if email and password:
        print("  Auto-filling credentials...")
        try:
            email_input = wait_for_element(
                driver, By.CSS_SELECTOR,
                'input[type="email"], input[name="email"], input[placeholder*="email" i]',
                timeout=15, description="email field"
            )
            email_input.clear()
            email_input.send_keys(email)
            time.sleep(0.5)

            pass_input = driver.find_element(
                By.CSS_SELECTOR,
                'input[type="password"], input[name="password"]'
            )
            pass_input.clear()
            pass_input.send_keys(password)
            time.sleep(0.5)

            # Try clicking a login/sign-in button
            for selector in [
                'button[type="submit"]',
                '//button[contains(text(), "Log")]',
                '//button[contains(text(), "Sign")]',
            ]:
                try:
                    if selector.startswith("//"):
                        btn = driver.find_element(By.XPATH, selector)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    break
                except Exception:
                    continue

        except Exception as e:
            print(f"  Auto-login failed ({e}), please log in manually.")

    # Wait up to 30 seconds for the user to finish logging in
    print("  Waiting up to 30 seconds for login to complete...")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: "/login" not in d.current_url and "/signup" not in d.current_url
        )
        print("  Logged in successfully!")
    except Exception:
        print("  WARNING: Still on login page after 30 seconds.")
        print("  Please log in manually. Waiting another 90 seconds...")
        WebDriverWait(driver, 90).until(
            lambda d: "/login" not in d.current_url and "/signup" not in d.current_url
        )
        print("  Logged in successfully!")
    time.sleep(3)


def create_video_from_text(driver, text, title, downloads_dir):
    """Create a single video using the HeyGen Video Agent page.

    Steps:
    1. Navigate to /video-agent
    2. Switch mode from Chat to Generate
    3. Paste the script text into the input area
    4. Click the submit button
    5. Wait for video generation to complete
    6. Download the video
    """
    print(f"\n  Creating video: '{title}'")

    # Step 1: Navigate to the Video Agent page
    print("  Step 1: Opening Video Agent...")
    driver.get(f"{HEYGEN_URL}/video-agent")
    time.sleep(5)

    # Step 2: Switch to "Generate" mode (default is "Chat")
    print("  Step 2: Switching to Generate mode...")
    generate_selected = False
    try:
        # Click the "Chat" dropdown button to open the mode menu
        for selector in [
            '//button[contains(text(), "Chat")]',
            '//div[contains(text(), "Chat")]//ancestor::button',
            '//span[contains(text(), "Chat")]//ancestor::button',
            # Look for a dropdown trigger near "Chat" text
            '//*[contains(text(), "Chat")]/parent::*[self::button or self::div[@role="button"]]',
        ]:
            try:
                els = driver.find_elements(By.XPATH, selector)
                for el in els:
                    if el.is_displayed():
                        el.click()
                        time.sleep(1)
                        # Now click "Generate" from the dropdown
                        for gen_sel in [
                            '//div[contains(text(), "Generate")]',
                            '//span[contains(text(), "Generate")]',
                            '//*[contains(text(), "Generate")]',
                        ]:
                            try:
                                gen_els = driver.find_elements(By.XPATH, gen_sel)
                                for gen_el in gen_els:
                                    if gen_el.is_displayed():
                                        gen_el.click()
                                        generate_selected = True
                                        print("    Generate mode selected.")
                                        break
                                if generate_selected:
                                    break
                            except Exception:
                                continue
                        break
                if generate_selected:
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"    Mode switch note: {e}")

    if not generate_selected:
        print("    WARNING: Could not switch to Generate mode automatically.")
        print("    Please switch to Generate mode manually if needed.")

    time.sleep(2)

    # Step 3: Paste script text into the input area
    print("  Step 3: Entering script text...")
    script_entered = False

    for selector in [
        'textarea[placeholder*="video idea" i]',
        'textarea[placeholder*="Describe" i]',
        'textarea[placeholder*="idea" i]',
        'div[contenteditable="true"]',
        'div[role="textbox"]',
        'textarea',
    ]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                if el.is_displayed():
                    el.click()
                    time.sleep(0.5)
                    # Clear existing text
                    el.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.2)
                    el.send_keys(Keys.DELETE)
                    time.sleep(0.2)
                    # Type text using JS for reliability with long text
                    if el.tag_name == "textarea":
                        driver.execute_script(
                            "arguments[0].value = arguments[1]; "
                            "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                            el, text
                        )
                    else:
                        driver.execute_script(
                            "arguments[0].innerText = arguments[1]; "
                            "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                            el, text
                        )
                    script_entered = True
                    print(f"    Script entered ({len(text)} chars).")
                    break
            if script_entered:
                break
        except Exception:
            continue

    if not script_entered:
        print("    WARNING: Could not find text input field!")
        print("    Please enter the script manually.")
        print(f"    Text: {text[:100]}...")
        input("    Press Enter when done...")

    time.sleep(1)

    # Step 4: Click the submit/send button (the circular arrow icon)
    print("  Step 4: Submitting for generation...")
    submitted = False
    for selector in [
        'button[type="submit"]',
        'button[aria-label*="send" i]',
        'button[aria-label*="submit" i]',
        'button[aria-label*="generate" i]',
        # The circular arrow button next to the textarea
        '//button[contains(@class, "send") or contains(@class, "submit")]',
        # SVG-based button (the arrow icon)
        '//textarea/ancestor::form//button',
        '//textarea/following::button[1]',
        # Fallback: buttons near the text input
        '//div[contains(@class, "input")]//button',
    ]:
        try:
            if selector.startswith("//"):
                els = driver.find_elements(By.XPATH, selector)
            else:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    submitted = True
                    print("    Video submitted for generation!")
                    break
            if submitted:
                break
        except Exception:
            continue

    if not submitted:
        print("    WARNING: Could not find submit button!")
        input("    Please click the submit button manually, then press Enter...")

    time.sleep(5)

    # Step 5: Wait for video generation and download
    print("  Step 5: Waiting for video generation...")
    download_video_from_heygen(driver, title, downloads_dir)


def download_video_from_heygen(driver, title, downloads_dir):
    """Wait for video generation on the Video Agent page and download it.

    The Video Agent generates the video inline on the same page.
    We wait for a video player or download link to appear, then download.
    If that fails, we check /videos as a fallback.
    """
    downloads_dir.mkdir(parents=True, exist_ok=True)
    output_path = downloads_dir / f"{title}.mp4"

    print("    Waiting for video to finish generating...")
    start_time = time.time()

    while time.time() - start_time < VIDEO_WAIT:
        time.sleep(10)
        elapsed = int(time.time() - start_time)

        try:
            # Check if a video element appeared on the page
            video_els = driver.find_elements(By.TAG_NAME, "video")
            for vel in video_els:
                src = vel.get_attribute("src")
                if src and src.startswith("http"):
                    print(f"    Video ready! Downloading...")
                    urllib.request.urlretrieve(src, str(output_path))
                    print(f"    Saved: {output_path}")
                    return

            # Check for source elements inside video tags
            source_els = driver.find_elements(By.CSS_SELECTOR, "video source")
            for sel_el in source_els:
                src = sel_el.get_attribute("src")
                if src and src.startswith("http"):
                    print(f"    Video ready! Downloading...")
                    urllib.request.urlretrieve(src, str(output_path))
                    print(f"    Saved: {output_path}")
                    return

            # Look for a download button on the page
            for selector in [
                '//button[contains(text(), "Download")]',
                '//a[contains(text(), "Download")]',
                '[aria-label*="download" i]',
                '[data-testid*="download" i]',
            ]:
                try:
                    if selector.startswith("//"):
                        els = driver.find_elements(By.XPATH, selector)
                    else:
                        els = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            el.click()
                            time.sleep(5)
                            print("    Download initiated!")
                            wait_for_download(downloads_dir, title)
                            return
                except Exception:
                    continue

            # Still waiting
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(w in page_text for w in ["generating", "processing", "creating", "loading"]):
                print(f"    Still generating... ({elapsed}s elapsed)")
            elif "failed" in page_text or "error" in page_text:
                print("    Video generation may have failed!")
                break

        except Exception as e:
            print(f"    Check error: {e}")

    # Fallback: check the /videos page
    print("    Checking /videos page as fallback...")
    driver.get(f"{HEYGEN_URL}/videos")
    time.sleep(5)

    try:
        video_els = driver.find_elements(By.TAG_NAME, "video")
        for vel in video_els:
            src = vel.get_attribute("src")
            if src and src.startswith("http"):
                print(f"    Found video on /videos page, downloading...")
                urllib.request.urlretrieve(src, str(output_path))
                print(f"    Saved: {output_path}")
                return
    except Exception:
        pass

    print(f"    Could not auto-download video '{title}'.")
    print(f"    Please download it manually from {HEYGEN_URL}/videos")


def wait_for_download(downloads_dir, title, timeout=120):
    """Wait for a file to finish downloading in the downloads directory."""
    start = time.time()
    while time.time() - start < timeout:
        # Check for any new .mp4 files or partial downloads (.crdownload)
        mp4_files = list(downloads_dir.glob("*.mp4"))
        crdownload_files = list(downloads_dir.glob("*.crdownload"))

        if mp4_files and not crdownload_files:
            # Rename the most recent download to our desired filename
            latest = max(mp4_files, key=lambda f: f.stat().st_mtime)
            target = downloads_dir / f"{title}.mp4"
            if latest != target:
                latest.rename(target)
            print(f"    Saved: {target}")
            return

        time.sleep(2)

    print(f"    Download may not have completed within {timeout}s.")


def get_text_files(folder):
    """Get all .txt files in the given folder (non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)
    files = sorted(folder.glob("*.txt"))
    if not files:
        print(f"No .txt files found in '{folder}'.")
        sys.exit(1)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Create HeyGen videos from text files using browser automation."
    )
    parser.add_argument(
        "folder",
        help="Path to folder containing .txt files",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.environ.get("HEYGEN_HEADLESS") == "1",
        help="Run browser in headless mode (default: visible)",
    )

    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    text_files = get_text_files(folder)
    downloads_dir = folder / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(text_files)} text file(s) in '{folder}'")
    print(f"Videos will be saved to '{downloads_dir}'")
    print(f"Mode: Video Agent (Generate)\n")

    driver = create_driver(headless=args.headless, download_dir=downloads_dir)

    try:
        # Login first
        print("Step 1: Logging in to HeyGen...")
        login(driver)

        results = {"success": 0, "failed": 0}

        for i, txt_file in enumerate(text_files, 1):
            print(f"\n{'='*60}")
            print(f"File {i}/{len(text_files)}: {txt_file.name}")
            print(f"{'='*60}")

            text = txt_file.read_text(encoding="utf-8").strip()
            if not text:
                print(f"  Skipping empty file.")
                results["failed"] += 1
                continue

            title = txt_file.stem

            try:
                create_video_from_text(driver, text, title, downloads_dir)
                results["success"] += 1
            except Exception as e:
                print(f"  Error processing '{txt_file.name}': {e}")
                results["failed"] += 1

                # Take a screenshot for debugging
                try:
                    screenshot_path = downloads_dir / f"error_{title}.png"
                    driver.save_screenshot(str(screenshot_path))
                    print(f"  Screenshot saved: {screenshot_path}")
                except Exception:
                    pass

        print(f"\n{'='*60}")
        print(f"Done! Success: {results['success']}, Failed: {results['failed']}")
        print(f"Videos saved to: {downloads_dir}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
