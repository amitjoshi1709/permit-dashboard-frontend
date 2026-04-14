"""
Georgia OS/OW Permit Automation — gaprospermits.com

Scaffold: logs in, navigates to the permit form, fills contact info, and stops.
Future: will fill load dimensions, axle config, route, and vehicle details.

Portal: https://www.gaprospermits.com/
Credentials: GA_OSOW_USERNAME / GA_OSOW_PASSWORD from .env
"""

import os
import time
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://www.gaprospermits.com/"
SLOW_MO = 300
TIMEOUT = 30_000


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
# Error helper
# ---------------------------------------------------------------------------

class PermitError(Exception):
    def __init__(self, message: str, screenshot_path: str = None):
        super().__init__(message)
        self.screenshot_path = screenshot_path


def _fatal(page: Page, message: str):
    """Take error screenshot then raise PermitError."""
    print(f"\n  [FATAL] {message}")
    err_screenshot = None
    try:
        err_screenshot = _screenshot(page, "ERROR")
    except Exception:
        pass
    raise PermitError(message, err_screenshot)


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def _login(page: Page, username: str, password: str):
    """Navigate to portal and log in."""
    print("\n[ACT] Navigating to GA OS/OW portal...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _screenshot(page, "portal_loaded")

    # Fill username and password
    print("[ACT] Logging in...")
    try:
        page.fill('input[name="UserName"], input[id="UserName"], input[type="text"]', username, timeout=10_000)
        page.fill('input[name="Password"], input[id="Password"], input[type="password"]', password, timeout=5_000)
        print(f"  [FILL] Username: {username}")
        print(f"  [FILL] Password: ***")
    except PlaywrightTimeoutError:
        _fatal(page, "Login fields not found on portal page")

    # Click sign in / log in button
    try:
        page.locator('button:has-text("Log In"), button:has-text("Sign In"), input[type="submit"]').first.click()
        page.wait_for_load_state("networkidle", timeout=15_000)
        time.sleep(2)
    except PlaywrightTimeoutError:
        _fatal(page, "Login button not found or page did not load after login")

    _screenshot(page, "logged_in")
    print("[OK] Login successful")


def _accept_agreement(page: Page):
    """Click 'I understand and agree' button."""
    print("\n[ACT] Accepting terms agreement...")
    try:
        page.locator('text=I understand and agree').click(timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
        time.sleep(1.5)
    except PlaywrightTimeoutError:
        # May not always appear (already accepted in session)
        print("  [SKIP] Agreement page not found — may already be accepted")
        return

    _screenshot(page, "agreement_accepted")
    print("[OK] Agreement accepted")


def _click_new_permit(page: Page):
    """Click 'New Permit' button."""
    print("\n[ACT] Clicking New Permit...")
    try:
        page.locator('text=New Permit').first.click(timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
        time.sleep(1.5)
    except PlaywrightTimeoutError:
        _fatal(page, "'New Permit' button not found")

    _screenshot(page, "new_permit_clicked")
    print("[OK] New Permit page loaded")


def _click_i_know_which_permit(page: Page):
    """Click 'I know which permit I need' button."""
    print("\n[ACT] Clicking 'I know which permit I need'...")
    try:
        page.locator('text=I know which permit I need').first.click(timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
        time.sleep(1.5)
    except PlaywrightTimeoutError:
        _fatal(page, "'I know which permit I need' button not found")

    _screenshot(page, "permit_type_selected")
    print("[OK] Permit selection page loaded")


def _fill_contact_info(page: Page, company: dict):
    """Fill contact name, phone, and email."""
    print("\n[ACT] Filling contact information...")

    contact_name = "Michael"
    contact_phone = ""  # TODO: add to company config if needed
    contact_email = company.get("primary_email", "") if company else ""

    try:
        # Try common field patterns — actual selectors may need adjustment
        # after inspecting the live portal
        name_fields = page.locator('input[name*="contact" i], input[name*="name" i], input[placeholder*="name" i]')
        if name_fields.count() > 0:
            name_fields.first.fill(contact_name)
            print(f"  [FILL] Contact Name: {contact_name}")

        phone_fields = page.locator('input[name*="phone" i], input[type="tel"], input[placeholder*="phone" i]')
        if phone_fields.count() > 0 and contact_phone:
            phone_fields.first.fill(contact_phone)
            print(f"  [FILL] Phone: {contact_phone}")

        email_fields = page.locator('input[name*="email" i], input[type="email"], input[placeholder*="email" i]')
        if email_fields.count() > 0 and contact_email:
            email_fields.first.fill(contact_email)
            print(f"  [FILL] Email: {contact_email}")
    except Exception as e:
        print(f"  [WARN] Could not fill some contact fields: {e}")

    _screenshot(page, "contact_info_filled")
    print("[STOP] =============================================")
    print("[STOP] Contact info page reached — stopping here.")
    print("[STOP] =============================================\n")


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
    Run the Georgia OS/OW permit automation for one driver.

    Currently a scaffold — logs in, navigates to the permit form,
    fills contact info, and stops. Future versions will fill load
    dimensions, axle config, route, and vehicle details.
    """
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "os_ow")
    load_details = permit.get("extraFields") or permit.get("loadDetails")

    # Credentials
    username = os.getenv("GA_OSOW_USERNAME")
    password = os.getenv("GA_OSOW_PASSWORD")
    if not username or not password:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": "Missing GA_OSOW_USERNAME or GA_OSOW_PASSWORD in .env",
        }

    print(f"[GA-OSOW] Starting permit {permit_id} for {driver_name} ({tractor})")
    if load_details:
        print(f"[GA-OSOW] Load: {load_details.get('width','?')}W x {load_details.get('height','?')}H x {load_details.get('length','?')}L, {load_details.get('weight','?')} lbs, {load_details.get('axleCount','?')} axles")

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
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            _login(page, username, password)
            _accept_agreement(page)
            _click_new_permit(page)
            _click_i_know_which_permit(page)
            _fill_contact_info(page, company)

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Reached contact info page — scaffold complete",
            }

        except PermitError as e:
            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": str(e),
            }
        except Exception as e:
            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": f"Unexpected: {e}",
            }
        finally:
            time.sleep(3)
            try:
                browser.close()
            except Exception:
                pass
