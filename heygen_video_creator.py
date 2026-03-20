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

    # DEBUG: Dump the toolbar / input area HTML so we can inspect element structure
    downloads_dir.mkdir(parents=True, exist_ok=True)
    debug_html_path = downloads_dir / "debug_toolbar_html.txt"
    try:
        toolbar_html = driver.execute_script("""
            // Capture a broad area around the input/toolbar
            var dumps = [];

            // 1. Get the full page HTML of interactive areas
            // Look for the textarea and its parent containers
            var textareas = document.querySelectorAll('textarea');
            textareas.forEach(function(ta, i) {
                // Go up several levels to capture the toolbar context
                var parent = ta;
                for (var j = 0; j < 8; j++) {
                    if (parent.parentElement) parent = parent.parentElement;
                }
                dumps.push('=== TEXTAREA #' + i + ' ANCESTOR (8 levels up) ===');
                dumps.push(parent.outerHTML);
            });

            // 2. Find all elements containing "Auto" text
            var autoEls = [];
            var walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false);
            while (walker.nextNode()) {
                if (walker.currentNode.textContent.trim() === 'Auto') {
                    var el = walker.currentNode.parentElement;
                    dumps.push('=== ELEMENT WITH "Auto" TEXT ===');
                    // Go up 4 levels
                    var ancestor = el;
                    for (var k = 0; k < 4; k++) {
                        if (ancestor.parentElement) ancestor = ancestor.parentElement;
                    }
                    dumps.push('Tag: ' + el.tagName + ', Class: ' + el.className);
                    dumps.push('Ancestor HTML: ' + ancestor.outerHTML.substring(0, 2000));
                    dumps.push('---');
                }
            }

            // 3. Find all elements containing "Portrait" or "Landscape" text
            var walker2 = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false);
            while (walker2.nextNode()) {
                var txt = walker2.currentNode.textContent.trim();
                if (txt === 'Portrait' || txt === 'Landscape') {
                    var el2 = walker2.currentNode.parentElement;
                    dumps.push('=== ELEMENT WITH "' + txt + '" TEXT ===');
                    var ancestor2 = el2;
                    for (var m = 0; m < 3; m++) {
                        if (ancestor2.parentElement) ancestor2 = ancestor2.parentElement;
                    }
                    dumps.push('Tag: ' + el2.tagName + ', Class: ' + el2.className);
                    dumps.push('Ancestor HTML: ' + ancestor2.outerHTML.substring(0, 2000));
                    dumps.push('---');
                }
            }

            // 4. Find all buttons/clickable elements in the page
            var buttons = document.querySelectorAll('button, [role="button"], a[href]');
            dumps.push('=== ALL BUTTONS/CLICKABLE ELEMENTS ===');
            buttons.forEach(function(btn, idx) {
                if (btn.offsetParent !== null) {  // visible only
                    var rect = btn.getBoundingClientRect();
                    dumps.push('BTN#' + idx + ' tag=' + btn.tagName +
                        ' class="' + (btn.className || '').substring(0, 100) + '"' +
                        ' aria-label="' + (btn.getAttribute('aria-label') || '') + '"' +
                        ' text="' + btn.textContent.trim().substring(0, 50) + '"' +
                        ' pos=(' + Math.round(rect.x) + ',' + Math.round(rect.y) +
                        ') size=' + Math.round(rect.width) + 'x' + Math.round(rect.height));
                }
            });

            return dumps.join('\\n');
        """)
        debug_html_path.write_text(toolbar_html)
        print(f"  DEBUG: Toolbar HTML saved to {debug_html_path}")
    except Exception as e:
        print(f"  DEBUG: Could not dump toolbar HTML: {e}")

    # Step 3: Set aspect ratio to Portrait
    # The toolbar has two "Auto" dropdowns. The second one (aspect ratio icon)
    # controls orientation with options: Auto, Portrait, Landscape.
    print("  Step 3: Setting aspect ratio to Portrait...")
    portrait_selected = False
    try:
        # Use JavaScript to find all clickable elements containing "Auto" text
        # in the toolbar area. The aspect ratio dropdown is the second one.
        auto_buttons = driver.execute_script("""
            var results = [];
            // Find all elements that contain exactly "Auto" text and are clickable
            var allEls = document.querySelectorAll('button, [role="button"], [class*="dropdown"], [class*="trigger"], [class*="select"]');
            allEls.forEach(function(el) {
                if (el.offsetParent !== null && el.textContent.trim().indexOf('Auto') !== -1) {
                    // Only include elements whose direct text (not deep children) contains Auto
                    var directText = '';
                    el.childNodes.forEach(function(child) {
                        if (child.nodeType === 3) directText += child.textContent;
                    });
                    // Also check span/div children for "Auto"
                    var spans = el.querySelectorAll('span, div, p');
                    var hasAutoChild = false;
                    spans.forEach(function(s) {
                        if (s.textContent.trim() === 'Auto') hasAutoChild = true;
                    });
                    if (directText.trim() === 'Auto' || hasAutoChild || el.textContent.trim() === 'Auto') {
                        results.push(el);
                    }
                }
            });
            return results;
        """)
        print(f"    Found {len(auto_buttons)} 'Auto' buttons in toolbar")

        # Try each Auto button - click it, check if Portrait appears in dropdown
        for i, btn in enumerate(auto_buttons):
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.5)

                # Look for "Portrait" in the now-visible dropdown
                portrait_els = driver.find_elements(By.XPATH,
                    '//*[text()="Portrait" or text()=" Portrait"]')
                for p_el in portrait_els:
                    if p_el.is_displayed():
                        driver.execute_script("arguments[0].click();", p_el)
                        portrait_selected = True
                        print(f"    Portrait mode selected (button #{i+1}).")
                        break
                if portrait_selected:
                    break
                else:
                    # Close this dropdown by clicking elsewhere, try next button
                    driver.execute_script(
                        "document.body.click();")
                    time.sleep(0.5)
            except Exception as e:
                print(f"    Button #{i+1} error: {e}")
                continue

        if not portrait_selected:
            # Fallback: try clicking all visible elements with "Auto" text
            # using a broader search
            all_auto = driver.find_elements(By.XPATH,
                '//*[normalize-space(text())="Auto"]')
            print(f"    Fallback: found {len(all_auto)} elements with 'Auto' text")
            for i, el in enumerate(all_auto):
                try:
                    if not el.is_displayed():
                        continue
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(1.5)
                    portrait_els = driver.find_elements(By.XPATH,
                        '//*[normalize-space(text())="Portrait"]')
                    for p_el in portrait_els:
                        if p_el.is_displayed():
                            driver.execute_script("arguments[0].click();", p_el)
                            portrait_selected = True
                            print(f"    Portrait mode selected (fallback #{i+1}).")
                            break
                    if portrait_selected:
                        break
                    else:
                        driver.execute_script("document.body.click();")
                        time.sleep(0.5)
                except Exception:
                    continue
    except Exception as e:
        print(f"    Aspect ratio note: {e}")

    if not portrait_selected:
        print("    WARNING: Could not set Portrait mode automatically.")
        print("    Please set it manually if needed.")

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

    print("    Waiting for video to finish generating...")
    start_time = time.time()

    while time.time() - start_time < VIDEO_WAIT:
        time.sleep(10)
        elapsed = int(time.time() - start_time)

        try:
            # Check if video generation is complete by looking for the video player
            # or a download icon button in the top-right corner of the video page
            video_els = driver.find_elements(By.TAG_NAME, "video")
            has_video = any(vel.is_displayed() for vel in video_els)

            if has_video:
                # DEBUG: Dump the video page HTML for download button analysis
                debug_video_path = downloads_dir / "debug_video_page.txt"
                try:
                    video_page_html = driver.execute_script("""
                        var dumps = [];
                        // All buttons/links on the page
                        var els = document.querySelectorAll('button, a, [role="button"]');
                        dumps.push('=== ALL CLICKABLE ELEMENTS ON VIDEO PAGE ===');
                        els.forEach(function(el, idx) {
                            if (el.offsetParent !== null) {
                                var rect = el.getBoundingClientRect();
                                dumps.push('EL#' + idx + ' tag=' + el.tagName +
                                    ' class="' + (el.className || '').substring(0, 100) + '"' +
                                    ' aria-label="' + (el.getAttribute('aria-label') || '') + '"' +
                                    ' title="' + (el.getAttribute('title') || '') + '"' +
                                    ' href="' + (el.getAttribute('href') || '') + '"' +
                                    ' download="' + (el.getAttribute('download') || '') + '"' +
                                    ' text="' + el.textContent.trim().substring(0, 80) + '"' +
                                    ' pos=(' + Math.round(rect.x) + ',' + Math.round(rect.y) +
                                    ') size=' + Math.round(rect.width) + 'x' + Math.round(rect.height));
                            }
                        });
                        // Video elements
                        var videos = document.querySelectorAll('video');
                        dumps.push('\\n=== VIDEO ELEMENTS ===');
                        videos.forEach(function(v, idx) {
                            dumps.push('VIDEO#' + idx +
                                ' src="' + (v.src || '') + '"' +
                                ' currentSrc="' + (v.currentSrc || '') + '"');
                            var sources = v.querySelectorAll('source');
                            sources.forEach(function(s, j) {
                                dumps.push('  SOURCE#' + j + ' src="' + (s.src || '') + '"');
                            });
                        });
                        // SVG icons - find their parent clickable elements
                        var svgs = document.querySelectorAll('svg');
                        dumps.push('\\n=== SVG ICONS WITH CLICKABLE PARENTS ===');
                        svgs.forEach(function(svg, idx) {
                            var parent = svg.closest('a, button, [role="button"]');
                            if (parent && parent.offsetParent !== null) {
                                var rect = parent.getBoundingClientRect();
                                dumps.push('SVG#' + idx + ' parent_tag=' + parent.tagName +
                                    ' class="' + (parent.className || '').substring(0, 100) + '"' +
                                    ' aria-label="' + (parent.getAttribute('aria-label') || '') + '"' +
                                    ' pos=(' + Math.round(rect.x) + ',' + Math.round(rect.y) +
                                    ') size=' + Math.round(rect.width) + 'x' + Math.round(rect.height));
                            }
                        });
                        return dumps.join('\\n');
                    """)
                    debug_video_path.write_text(video_page_html)
                    print(f"    DEBUG: Video page HTML saved to {debug_video_path}")
                except Exception as e:
                    print(f"    DEBUG: Could not dump video page: {e}")

                print(f"    Video detected on page! ({elapsed}s elapsed)")

                # First try: click the download icon button (top-right corner)
                # It's typically an SVG icon button with a download arrow
                download_clicked = False
                for selector in [
                    '[aria-label*="download" i]',
                    '[aria-label*="Download" i]',
                    '[data-testid*="download" i]',
                    'a[download]',
                    # SVG download icon buttons - look for path with download arrow shape
                    '//button[.//*[local-name()="svg"]]',
                    '//a[.//*[local-name()="svg"]]',
                    '//button[contains(@class, "download")]',
                    '//a[contains(@class, "download")]',
                    '//button[contains(text(), "Download")]',
                    '//a[contains(text(), "Download")]',
                ]:
                    try:
                        if selector.startswith("//"):
                            els = driver.find_elements(By.XPATH, selector)
                        else:
                            els = driver.find_elements(By.CSS_SELECTOR, selector)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                # Check if it looks like a download button
                                # (small icon button in top area of page)
                                aria = (el.get_attribute("aria-label") or "").lower()
                                cls = (el.get_attribute("class") or "").lower()
                                href = (el.get_attribute("href") or "").lower()
                                title_attr = (el.get_attribute("title") or "").lower()
                                if any(kw in s for kw in ["download"] for s in [aria, cls, href, title_attr]):
                                    driver.execute_script("arguments[0].click();", el)
                                    download_clicked = True
                                    print("    Download button clicked!")
                                    time.sleep(5)
                                    break
                        if download_clicked:
                            break
                    except Exception:
                        continue

                if download_clicked:
                    wait_for_download(downloads_dir, title)
                    return

                # Second try: use JavaScript to find the download icon by checking
                # all small buttons/links near the top of the page
                print("    Trying JS-based download button search...")
                download_clicked = driver.execute_script("""
                    // Look for links/buttons with download-related attributes or
                    // SVG icons that look like download arrows
                    var candidates = document.querySelectorAll('a, button');
                    for (var i = 0; i < candidates.length; i++) {
                        var el = candidates[i];
                        if (!el.offsetParent) continue;
                        var aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        var title = (el.getAttribute('title') || '').toLowerCase();
                        var cls = (el.className || '').toLowerCase();
                        var href = (el.getAttribute('href') || '').toLowerCase();
                        var download = el.getAttribute('download');
                        if (aria.indexOf('download') !== -1 ||
                            title.indexOf('download') !== -1 ||
                            cls.indexOf('download') !== -1 ||
                            download !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                """)
                if download_clicked:
                    print("    Download button clicked via JS!")
                    time.sleep(5)
                    wait_for_download(downloads_dir, title)
                    return

                # Third try: get video src and download directly
                for vel in video_els:
                    src = vel.get_attribute("src")
                    if src and src.startswith("http"):
                        print(f"    Downloading video from src URL...")
                        urllib.request.urlretrieve(src, str(output_path))
                        print(f"    Saved: {output_path}")
                        return
                source_els = driver.find_elements(By.CSS_SELECTOR, "video source")
                for sel_el in source_els:
                    src = sel_el.get_attribute("src")
                    if src and src.startswith("http"):
                        print(f"    Downloading video from source URL...")
                        urllib.request.urlretrieve(src, str(output_path))
                        print(f"    Saved: {output_path}")
                        return

                # Fourth try: use browser's built-in download via the download icon
                # From the screenshot, the icon is at top-right, likely an <a> tag
                # Try clicking any icon-like element near the title area
                print("    Trying to find download icon near video title...")
                download_clicked = driver.execute_script("""
                    // The download icon is at the top-right of the video detail page
                    // Look for clickable SVG icons
                    var svgs = document.querySelectorAll('svg');
                    for (var i = 0; i < svgs.length; i++) {
                        var svg = svgs[i];
                        if (!svg.offsetParent) continue;
                        var parent = svg.closest('a, button, [role="button"]');
                        if (!parent) continue;
                        // Check position - should be in upper right area
                        var rect = parent.getBoundingClientRect();
                        if (rect.top < 100 && rect.right > window.innerWidth - 200) {
                            // This is likely a top-right icon button
                            // Check if it's the first one (download) not the second (share)
                            parent.click();
                            return true;
                        }
                    }
                    return false;
                """)
                if download_clicked:
                    print("    Top-right icon clicked (likely download)!")
                    time.sleep(5)
                    wait_for_download(downloads_dir, title)
                    return

                print("    WARNING: Video found but could not trigger download.")
                print("    Attempting to extract video URL from network...")

                # Last resort: get all video URLs from page via JS
                video_url = driver.execute_script("""
                    var videos = document.querySelectorAll('video');
                    for (var i = 0; i < videos.length; i++) {
                        var v = videos[i];
                        if (v.src && v.src.startsWith('http')) return v.src;
                        var sources = v.querySelectorAll('source');
                        for (var j = 0; j < sources.length; j++) {
                            if (sources[j].src && sources[j].src.startsWith('http'))
                                return sources[j].src;
                        }
                        // Try currentSrc
                        if (v.currentSrc && v.currentSrc.startsWith('http'))
                            return v.currentSrc;
                    }
                    return null;
                """)
                if video_url:
                    print(f"    Downloading from extracted URL...")
                    urllib.request.urlretrieve(video_url, str(output_path))
                    print(f"    Saved: {output_path}")
                    return

                print("    Could not extract video URL. Please download manually.")
                break

            # Still waiting - no video element yet
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
        # Look for download button on /videos page too
        for selector in [
            '[aria-label*="download" i]',
            'a[download]',
            '//button[contains(text(), "Download")]',
            '//a[contains(text(), "Download")]',
        ]:
            try:
                if selector.startswith("//"):
                    els = driver.find_elements(By.XPATH, selector)
                else:
                    els = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(5)
                        print("    Download initiated from /videos page!")
                        wait_for_download(downloads_dir, title)
                        return
            except Exception:
                continue

        video_els = driver.find_elements(By.TAG_NAME, "video")
        for vel in video_els:
            src = vel.get_attribute("src") or vel.get_attribute("currentSrc")
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
