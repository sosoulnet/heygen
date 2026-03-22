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

    If a login/register page is detected, pauses and waits for the user
    to complete login manually. Never auto-fills credentials.
    """
    driver.get(HEYGEN_URL)
    print("  Navigated to HeyGen...")
    time.sleep(3)

    # Check if already logged in (no login/signup in the URL)
    if "/login" not in driver.current_url and "/signup" not in driver.current_url:
        print("  Already logged in!")
        return

    print("  Login/register page detected.")
    print("  Please log in manually in the browser window.")
    input("  Press Enter here once you have logged in successfully...")

    # Verify login succeeded
    time.sleep(2)
    if "/login" in driver.current_url or "/signup" in driver.current_url:
        print("  Still on login page. Waiting for redirect...")
        try:
            WebDriverWait(driver, 120).until(
                lambda d: "/login" not in d.current_url and "/signup" not in d.current_url
            )
            print("  Logged in successfully!")
        except Exception:
            print("  WARNING: Still on login page. Continuing anyway...")
    else:
        print("  Logged in successfully!")
    time.sleep(3)


def create_video_from_text(driver, text, title, downloads_dir):
    """Create a single video using the HeyGen Video Agent page.

    Steps:
    1. Navigate to /video-agent
    2. Switch mode from Chat to Generate
    3. Set aspect ratio to Portrait
    4. Paste the script text into the input area
    5. Click the submit button
    6. Wait for video generation to complete and download
    """
    print(f"\n  Creating video: '{title}'")

    # Step 1: Navigate to the Video Agent page and wait for user to be ready
    print("  Step 1: Opening Video Agent...")
    driver.get(f"{HEYGEN_URL}/video-agent")
    time.sleep(3)
    print("  Page loaded. Please log in if needed and make sure you are on the Video Agent page.")
    input("  Press Enter when you are ready to continue...")

    # Step 2: Switch to "Generate" mode (default is "Chat")
    # The "Chat" toggle is a div with class tw-h-8 tw-cursor-pointer in the
    # toolbar below the textarea (around y=362).
    print("  Step 2: Switching to Generate mode...")
    generate_selected = False
    try:
        # Find the "Chat" div in the toolbar using JS
        chat_el = driver.execute_script("""
            var els = document.querySelectorAll('div.tw-cursor-pointer');
            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                if (el.offsetParent && el.textContent.trim() === 'Chat' &&
                    el.classList.contains('tw-h-8')) {
                    return el;
                }
            }
            return null;
        """)
        if chat_el:
            driver.execute_script("arguments[0].click();", chat_el)
            time.sleep(1.5)
            # Click "Generate" from the dropdown
            gen_el = driver.execute_script("""
                var els = document.querySelectorAll('div, span');
                for (var i = 0; i < els.length; i++) {
                    var el = els[i];
                    if (el.offsetParent && el.textContent.trim() === 'Generate') {
                        return el;
                    }
                }
                return null;
            """)
            if gen_el:
                driver.execute_script("arguments[0].click();", gen_el)
                generate_selected = True
                print("    Generate mode selected.")
            else:
                print("    Could not find 'Generate' option in dropdown.")
        else:
            print("    Could not find 'Chat' toggle button.")
    except Exception as e:
        print(f"    Mode switch error: {e}")

    if not generate_selected:
        print("    WARNING: Could not switch to Generate mode automatically.")

    time.sleep(2)

    # Step 3: Set aspect ratio to Portrait
    # The toolbar below the textarea has two "Auto" divs with class
    # tw-h-8 tw-cursor-pointer. The second one is the aspect ratio dropdown.
    print("  Step 3: Setting aspect ratio to Portrait...")
    portrait_selected = False
    try:
        # Find the two "Auto" toolbar dropdowns (tw-h-8 tw-cursor-pointer divs
        # that contain "Auto" text). These are in the toolbar, distinct from the
        # Avatar/Style "Auto" elements higher on the page.
        aspect_btn = driver.execute_script("""
            var textarea = document.querySelector('textarea');
            if (!textarea) return null;
            var taRect = textarea.getBoundingClientRect();

            // Find tw-h-8 tw-cursor-pointer divs with "Auto" text
            // that are BELOW the textarea (toolbar area)
            var candidates = [];
            var els = document.querySelectorAll('div.tw-cursor-pointer');
            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                if (!el.offsetParent) continue;
                if (!el.classList.contains('tw-h-8')) continue;
                var rect = el.getBoundingClientRect();
                // Must be below the textarea (toolbar is below input)
                if (rect.top > taRect.bottom - 5 && el.textContent.trim() === 'Auto') {
                    candidates.push(el);
                }
            }
            // The second "Auto" in the toolbar is the aspect ratio dropdown
            if (candidates.length >= 2) return candidates[1];
            if (candidates.length === 1) return candidates[0];
            return null;
        """)
        if aspect_btn:
            driver.execute_script("arguments[0].click();", aspect_btn)
            time.sleep(1.5)
            # Click "Portrait" from the dropdown
            portrait_el = driver.execute_script("""
                var els = document.querySelectorAll('div, span');
                for (var i = 0; i < els.length; i++) {
                    var el = els[i];
                    if (el.offsetParent && el.textContent.trim() === 'Portrait') {
                        return el;
                    }
                }
                return null;
            """)
            if portrait_el:
                driver.execute_script("arguments[0].click();", portrait_el)
                portrait_selected = True
                print("    Portrait mode selected.")
            else:
                print("    Could not find 'Portrait' option in dropdown.")
        else:
            print("    Could not find aspect ratio dropdown.")
    except Exception as e:
        print(f"    Aspect ratio error: {e}")

    if not portrait_selected:
        print("    WARNING: Could not set Portrait mode automatically.")

    time.sleep(1)

    # Step 4: Paste script text into the input area
    print("  Step 4: Entering script text...")
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
                    # Use React-compatible value setter + clipboard paste
                    # to ensure the full multi-line text is recognized
                    if el.tag_name == "textarea":
                        driver.execute_script("""
                            var el = arguments[0];
                            var text = arguments[1];
                            // Use React's native input value setter to bypass
                            // React's controlled component state
                            var nativeSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLTextAreaElement.prototype, 'value'
                            ).set;
                            nativeSetter.call(el, text);
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                        """, el, text)
                    else:
                        driver.execute_script(
                            "arguments[0].innerText = arguments[1]; "
                            "arguments[0].dispatchEvent(new Event('input', {bubbles: true})); "
                            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                            el, text
                        )
                    time.sleep(0.5)
                    # Verify the text was set correctly
                    actual = driver.execute_script(
                        "return arguments[0].value || arguments[0].innerText;", el
                    )
                    if actual and len(actual.strip()) > 20:
                        script_entered = True
                        print(f"    Script entered ({len(text)} chars, verified {len(actual)} chars in field).")
                    else:
                        # Fallback: use clipboard paste via JS
                        print("    React setter didn't stick, trying clipboard paste...")
                        el.click()
                        time.sleep(0.3)
                        el.send_keys(Keys.CONTROL + "a")
                        time.sleep(0.1)
                        el.send_keys(Keys.DELETE)
                        time.sleep(0.1)
                        # Copy text to clipboard via JS and paste
                        driver.execute_script(
                            "navigator.clipboard.writeText(arguments[0]);", text
                        )
                        time.sleep(0.3)
                        el.send_keys(Keys.CONTROL + "v")
                        time.sleep(0.5)
                        script_entered = True
                        print(f"    Script pasted via clipboard ({len(text)} chars).")
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

    # Step 5: Click the submit/send button (the circular arrow icon)
    print("  Step 5: Submitting for generation...")
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
    print("  Step 6: Waiting for video generation...")
    download_video_from_heygen(driver, title, downloads_dir)


def download_video_from_heygen(driver, title, downloads_dir):
    """Wait for video generation on the Video Agent page and download it.

    The Video Agent generates the video inline on the same page.
    We wait for a video player or download link to appear, then download.
    If that fails, we check /videos as a fallback.
    """
    downloads_dir.mkdir(parents=True, exist_ok=True)
    output_path = downloads_dir / f"{title}.mp4"

    # Snapshot existing generated_videos URLs so we can detect the NEW one
    existing_urls = set(driver.execute_script("""
        var videos = document.querySelectorAll('video');
        var urls = [];
        for (var i = 0; i < videos.length; i++) {
            var src = videos[i].src || '';
            if (src.indexOf('generated_videos') !== -1) urls.push(src.split('?')[0]);
        }
        return urls;
    """) or [])
    print(f"    DEBUG: {len(existing_urls)} existing generated_videos URL(s):")
    for u in existing_urls:
        print(f"      {u}")

    # Also snapshot ALL video src URLs for debugging
    all_video_srcs = driver.execute_script("""
        return Array.from(document.querySelectorAll('video')).map(function(v, i) {
            return {i: i, src: (v.src || '').substring(0, 120),
                    displayed: v.offsetParent !== null,
                    w: v.offsetWidth, h: v.offsetHeight};
        });
    """) or []
    print(f"    DEBUG: All {len(all_video_srcs)} video elements at start:")
    for v in all_video_srcs:
        print(f"      [{v['i']}] {v['w']}x{v['h']} displayed={v['displayed']} src={v['src']}")

    print("    Waiting for video to finish generating...")
    start_time = time.time()

    while time.time() - start_time < VIDEO_WAIT:
        time.sleep(10)
        elapsed = int(time.time() - start_time)

        try:
            # DEBUG: dump all video srcs each poll
            current_srcs = driver.execute_script("""
                return Array.from(document.querySelectorAll('video')).map(function(v, i) {
                    return {i: i, src: (v.src || '').substring(0, 150),
                            displayed: v.offsetParent !== null,
                            w: v.offsetWidth, h: v.offsetHeight};
                });
            """) or []
            print(f"    DEBUG [{elapsed}s]: {len(current_srcs)} video elements:")
            for v in current_srcs:
                is_new = ("generated_videos" in v["src"] and
                          v["src"].split("?")[0] not in existing_urls)
                marker = " *** NEW ***" if is_new else ""
                print(f"      [{v['i']}] {v['w']}x{v['h']} disp={v['displayed']} "
                      f"src={v['src']}{marker}")

            # Scan all <video> elements for a NEW generated_videos .mp4 URL
            # that wasn't on the page before we submitted.
            video_url = driver.execute_script("""
                var existing = arguments[0];
                var videos = document.querySelectorAll('video');
                for (var i = 0; i < videos.length; i++) {
                    var src = videos[i].src || '';
                    if (src.indexOf('generated_videos') !== -1) {
                        var base = src.split('?')[0];
                        if (existing.indexOf(base) === -1) return src;
                    }
                }
                return null;
            """, list(existing_urls))

            if video_url:
                print(f"    New generated video detected! ({elapsed}s elapsed)")
                print(f"    DEBUG: URL = {video_url[:200]}")

                # Use fetch() + blob + <a download> to force the browser to
                # save the file (window.open would just play it in a tab).
                print(f"    Downloading via browser fetch...")
                download_filename = f"{title}.mp4"

                # Run fetch and capture success/failure via a window flag
                driver.execute_script("""
                    window.__downloadStatus = 'fetching';
                    var url = arguments[0];
                    var filename = arguments[1];
                    console.log('DOWNLOAD: starting fetch for ' + url.substring(0, 100));
                    fetch(url)
                        .then(function(r) {
                            console.log('DOWNLOAD: fetch response status=' + r.status +
                                        ' ok=' + r.ok + ' type=' + r.headers.get('content-type'));
                            window.__downloadStatus = 'status=' + r.status;
                            if (!r.ok) throw new Error('HTTP ' + r.status);
                            return r.blob();
                        })
                        .then(function(blob) {
                            console.log('DOWNLOAD: blob size=' + blob.size + ' type=' + blob.type);
                            window.__downloadStatus = 'blob_size=' + blob.size;
                            var a = document.createElement('a');
                            a.href = URL.createObjectURL(blob);
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            window.__downloadStatus = 'clicked_size=' + blob.size;
                        })
                        .catch(function(err) {
                            console.error('DOWNLOAD ERROR: ' + err);
                            window.__downloadStatus = 'error=' + err.message;
                        });
                """, video_url, download_filename)

                # Poll the download status flag
                for i in range(30):
                    time.sleep(2)
                    status = driver.execute_script("return window.__downloadStatus;")
                    print(f"    DEBUG: download status = {status}")
                    if status and ("clicked_size=" in str(status) or
                                   "error=" in str(status)):
                        break

                # Check browser console logs
                try:
                    logs = driver.get_log("browser")
                    dl_logs = [l for l in logs if "DOWNLOAD" in l.get("message", "")]
                    for log in dl_logs[-10:]:
                        print(f"    DEBUG console: {log['message'][:200]}")
                except Exception:
                    pass

                # List downloads directory
                dl_files = list(downloads_dir.glob("*"))
                print(f"    DEBUG: {len(dl_files)} files in downloads dir:")
                for f in dl_files:
                    print(f"      {f.name} ({f.stat().st_size} bytes)")

                wait_for_download(downloads_dir, title, timeout=180)
                return

            # Still waiting
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(w in page_text for w in
                   ["generating", "processing", "creating", "loading"]):
                print(f"    Still generating... ({elapsed}s elapsed)")
            elif "failed" in page_text or "error" in page_text:
                print("    Video generation may have failed!")
                break

        except Exception as e:
            import traceback
            print(f"    Check error: {e}")
            traceback.print_exc()

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
