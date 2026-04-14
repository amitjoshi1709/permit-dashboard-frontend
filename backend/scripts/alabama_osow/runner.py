"""
Alabama DOT — Annual Oversize/Overweight Permit Automation

Portal: https://alpass.dot.state.al.us/permits/login.asp
Permit type: Annual Oversize and/or Overweight (only)
Automation boundary: Fills all form fields and clicks Continue on
  the Application Review page. Does NOT proceed past that point.
  Payment is completed manually by a human.

Data flow:
  Backend builds permit dict (driver details from Supabase + company constants)
  → run() extracts what the form needs
  → Step functions log in, select permit type, fill the form
  → Stops at Application Review after clicking Continue
"""

import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://alpass.dot.state.al.us/permits/login.asp"
SLOW_MO = 300
TIMEOUT = 30_000

# Company driver types — use Mega Trucking's USDOT
COMPANY_TYPES = {"F", "LP"}


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------

_screenshot_counter = 0
_screenshot_dir = ""


def _reset_screenshots(job_id: str):
    global _screenshot_counter, _screenshot_dir
    _screenshot_counter = 0
    _screenshot_dir = str(Path(__file__).resolve().parent.parent.parent / "screenshots" / job_id)
    os.makedirs(_screenshot_dir, exist_ok=True)


def _screenshot(page: Page, name: str) -> str:
    global _screenshot_counter
    _screenshot_counter += 1
    prefix = str(_screenshot_counter).zfill(2)
    filepath = os.path.join(_screenshot_dir, f"{prefix}_{name}.png")
    page.screenshot(path=filepath, full_page=True)
    print(f"  [SCREENSHOT] {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_page_settle(page: Page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(1.5)


def _safe_fill(page: Page, selector: str, value: str, field_name: str) -> None:
    """Fill a text input, clicking it first to clear any existing value."""
    if not value:
        print(f"  [SKIP] {field_name}: empty value")
        return
    try:
        page.wait_for_selector(selector, timeout=8_000)
        locator = page.locator(selector).first
        locator.click(click_count=3)
        locator.fill(value)
        print(f'  [FILL] {field_name}: "{value}"')
    except Exception as e:
        print(f"  [WARN] Could not fill {field_name} ({selector}): {e}")


def _fill_by_label(page: Page, label_text: str, value: str) -> None:
    """Fill a field by its label text."""
    if not value:
        return
    try:
        page.get_by_label(label_text, exact=False).fill(value)
        print(f'  [FILL] "{label_text}": "{value}"')
    except Exception as e:
        print(f'  [WARN] Could not fill "{label_text}": {e}')


def _select_by_label(page: Page, label_text: str, value: str) -> None:
    """Select a dropdown option by label text."""
    if not value:
        return
    try:
        loc = page.get_by_label(label_text, exact=False)
        try:
            loc.select_option(value=value)
        except Exception:
            loc.select_option(label=value)
        print(f'  [SELECT] "{label_text}": "{value}"')
    except Exception as e:
        print(f'  [WARN] Could not select "{label_text}": {e}')


def _iso_to_mmddyyyy(date_str: str) -> str:
    """Convert YYYY-MM-DD to MM/DD/YYYY. Passes through MM/DD/YYYY as-is."""
    if not date_str:
        return ""
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", date_str):
        m, d, y = date_str.split("/")
        return f"{m.zfill(2)}/{d.zfill(2)}/{y}"
    parts = date_str.split("-")
    if len(parts) != 3:
        return date_str
    y, m, d = parts
    return f"{m.zfill(2)}/{d.zfill(2)}/{y}"


def debug_fields(page: Page) -> None:
    """Dump all visible form fields for debugging."""
    print("\n" + "=" * 70)
    print("DEBUG — form fields on this page:")
    print("=" * 70)
    fields = page.query_selector_all("input:not([type='hidden']), select, textarea")
    for el in fields:
        id_ = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        type_ = el.get_attribute("type") or ""
        label_text = ""
        if id_:
            lbl = page.query_selector(f"label[for='{id_}']")
            if lbl:
                label_text = lbl.inner_text().strip()
        if not label_text:
            label_text = el.get_attribute("aria-label") or ""
        print(
            f"  LABEL={label_text!r:38s} "
            f"id={id_!r:14s} "
            f"type={type_!r:12s} "
            f"name={name!r}"
        )
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Step functions — following portal documentation
# ---------------------------------------------------------------------------

def step_login(page: Page, username: str, password: str) -> None:
    """Step 1 — Navigate to portal and log in."""
    print("\n[STEP 1] Navigating to Alabama DOT OSOW portal and logging in...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _wait_for_page_settle(page)
    _screenshot(page, "login_page")

    debug_fields(page)

    # Try known selectors, fall back to generic
    username_selectors = [
        'input[name="username"]',
        'input[name="userName"]',
        'input[name="UserName"]',
        'input[id="username"]',
        'input[type="text"]',
    ]
    password_selectors = [
        'input[name="password"]',
        'input[name="Password"]',
        'input[id="password"]',
        'input[type="password"]',
    ]
    login_selectors = [
        'input[type="submit"][value="Login"]',
        'button:has-text("Login")',
        'a:has-text("Login"):near(input[name="Password"])',
        'a.login',
        'a:has-text("Login")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]

    # Fill username
    filled = False
    for sel in username_selectors:
        try:
            page.wait_for_selector(sel, timeout=3_000)
            page.locator(sel).first.fill(username)
            print(f'  [FILL] Username via {sel}')
            filled = True
            break
        except (PlaywrightTimeoutError, Exception):
            continue
    if not filled:
        raise Exception("Could not find username field on login page")

    # Fill password
    filled = False
    for sel in password_selectors:
        try:
            page.wait_for_selector(sel, timeout=3_000)
            page.locator(sel).first.fill(password)
            print(f'  [FILL] Password via {sel}')
            filled = True
            break
        except (PlaywrightTimeoutError, Exception):
            continue
    if not filled:
        raise Exception("Could not find password field on login page")

    # Click login — try role-based first (most reliable), then CSS selectors
    clicked = False
    try:
        page.get_by_role("link", name="Login", exact=True).click(timeout=5_000)
        print('  [CLICK] Login via role=link "Login"')
        clicked = True
    except Exception:
        for sel in login_selectors:
            try:
                page.locator(sel).first.click(timeout=5_000)
                print(f'  [CLICK] Login via {sel}')
                clicked = True
                break
            except Exception:
                continue
    if not clicked:
        raise Exception("Could not find Login button/link on login page")

    _wait_for_page_settle(page)
    _screenshot(page, "after_login")

    # Verify we left the login page
    if "login" in page.url.lower():
        # Could still be on login page with an error
        error_text = page.locator("body").inner_text()
        if "invalid" in error_text.lower() or "incorrect" in error_text.lower():
            raise Exception("Login failed — invalid credentials")
        # Might just be slow, give it more time
        page.wait_for_timeout(3000)

    print("[OK] Login complete")


def step_select_permit_type(page: Page) -> None:
    """Step 2 — Click 'Annual Oversize and/or Overweight' on the menu page."""
    print("\n[STEP 2] Selecting 'Annual Oversize and/or Overweight' permit type...")

    debug_fields(page)

    selectors = [
        'a:has-text("Annual Oversize and/or Overweight")',
        'text=Annual Oversize and/or Overweight',
        'a:has-text("Annual Oversize")',
        'a:has-text("Annual")',
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=5_000)
            page.click(sel)
            print(f'  [CLICK] {sel}')
            _wait_for_page_settle(page)
            _screenshot(page, "permit_type_selected")
            print("[OK] Permit type selected")
            return
        except PlaywrightTimeoutError:
            continue

    # If link selectors fail, try finding it in all visible links
    print("  [WARN] Standard selectors didn't match. Scanning all links...")
    links = page.query_selector_all("a")
    for link in links:
        text = (link.inner_text() or "").strip()
        print(f"    Link: {text!r}")
        if "annual" in text.lower() and "oversize" in text.lower():
            link.click()
            _wait_for_page_settle(page)
            _screenshot(page, "permit_type_selected")
            print(f'  [CLICK] Found and clicked: {text!r}')
            return

    _screenshot(page, "permit_type_NOT_FOUND")
    raise Exception("Could not find 'Annual Oversize and/or Overweight' link on menu page")


def step_fill_form(page: Page, vin: str, effective_date: str) -> None:
    """
    Fill the single-page permit form.

    The portal shows all sections on one page:
      Step 1 — Acknowledgement checkbox  (name='acknowledge', id='ackcheck')
      Step 2 — Vehicle/Load: VIN         (name='TrkSerial')
      Step 3 — Travel Dates: From date   (name='fromdate')
      Step 4 — Permit Attachments        (no required fields)
      Step 5 — Application Review: Continue button
    """
    print("\n[FORM] Filling single-page permit form...")

    debug_fields(page)
    _screenshot(page, "form_page")

    # ── Step 1: Acknowledgement checkbox ────────────────────────────
    print("\n  [SECTION] Step 1 — Acknowledgement")
    try:
        cb = page.locator('input#ackcheck[type="checkbox"]')
        cb.check()
        print('  [CHECK] Acknowledgement checkbox checked')
    except Exception as e:
        print(f"  [WARN] Could not check acknowledgement: {e}")

    # ── Step 2: Vehicle — VIN/Serial number ─────────────────────────
    print("\n  [SECTION] Step 2 — Vehicle and Load Information")
    _safe_fill(page, 'input[name="TrkSerial"][type="text"]', vin, "VIN/Serial #")

    _screenshot(page, "vin_filled")

    # ── Step 3: Travel Dates ────────────────────────────────────────
    print("\n  [SECTION] Step 3 — Travel Dates")
    date_formatted = _iso_to_mmddyyyy(effective_date)
    _safe_fill(page, 'input[name="fromdate"][type="text"]', date_formatted, "From Date")

    _screenshot(page, "form_filled")

    # ── Step 5: Application Review — click Continue ─────────────────
    print("\n  [SECTION] Step 5 — Application Review")
    continue_selectors = [
        'input[value="Continue"]',
        'button:has-text("Continue")',
        'a:has-text("Continue")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]
    clicked = False
    for sel in continue_selectors:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] Continue via {sel}')
            clicked = True
            _wait_for_page_settle(page)
            break
        except Exception:
            continue

    if not clicked:
        raise Exception("Could not find Continue button on Application Review")

    _screenshot(page, "after_continue")

    print("[STOP] =============================================")
    print("[STOP] Application Review validated — NOT proceeding")
    print("[STOP] to payment. Human takes over from here.")
    print("[STOP] =============================================")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    permit: dict,
    job_id: str,
    on_captcha_needed: Optional[Callable] = None,
    company: dict = None,
) -> dict:
    """
    Run the Alabama Annual OS/OW permit automation for one driver.

    Args:
        permit:           Enriched permit dict from the backend.
        job_id:           The parent job ID (for screenshots/logging).
        on_captcha_needed: Not used — kept for interface compatibility.
        company:          Company constants dict (not used for this portal —
                          only VIN, USDOT, and effective date are needed).

    Returns:
        Result dict with "status", "permitId", "driverName", etc.
    """
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")

    # Resolve USDOT: company drivers use Mega Trucking's, others use their own
    driver_type = driver.get("driverType", "")
    if driver_type in COMPANY_TYPES and company:
        usdot = "2582238"  # Mega Trucking LLC
    else:
        usdot = driver.get("usdot", "")

    vin = driver.get("vin", "")
    effective_date = permit.get("effectiveDate", "")

    # Validate required fields
    errors = []
    if not vin:
        errors.append("Missing VIN")
    if not usdot:
        errors.append("Missing USDOT")
    if not effective_date:
        errors.append("Missing effectiveDate")

    if errors:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": f"Validation failed: {'; '.join(errors)}",
        }

    # Credentials
    username = os.getenv("AL_USERNAME")
    password = os.getenv("AL_PASSWORD")
    if not username or not password:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": "Missing AL_USERNAME or AL_PASSWORD in .env",
        }

    print(f"[AL-OSOW] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[AL-OSOW] VIN: {vin} | USDOT: {usdot} | Eff. Date: {effective_date}")

    _reset_screenshots(job_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        context = browser.new_context(
            viewport=None,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            step_login(page, username, password)
            step_select_permit_type(page)
            step_fill_form(page, vin, effective_date)

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Application Review validated — stopped before payment",
            }

        except Exception as e:
            print(f"\n[AL-OSOW] Error for {driver_name}: {e}")
            _screenshot(page, "ERROR")
            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": str(e),
            }
        finally:
            time.sleep(3)
            try:
                browser.close()
            except Exception:
                pass
