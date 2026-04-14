"""
Arkansas DFA — Trip Permit Automation

Portal: https://airsdsmvpub.dfa.arkansas.gov/mydmv/_/
Permit type: Trip Permit (only)
Login: Not required — navigate directly and begin
Automation boundary: Fills all form fields through Payment Method and
  clicks Next. Does NOT click Submit or any payment confirmation button.
  Payment is completed manually by a human dispatcher.

Data flow:
  Backend builds permit dict (driver details from Supabase + company constants)
  → run() fills the multi-step form
  → Stops after Payment Method → Next
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

PORTAL_URL = "https://www.dfa.arkansas.gov/office/mydmv/"
SLOW_MO = 300
TIMEOUT = 30_000

# Hardcoded company address and contact info
ADDRESS = {
    "country":    "USA",
    "street":     "5979 NORTHWEST 151ST STREET",
    "unit_type":  "SUITE",
    "unit":       "101",
    "city":       "MIAMI LAKES",
    "state":      "FL - FLORIDA",
    "zip":        "33014-0000",
}

CONTACT = {
    "full_name":      "MEGA TRUCKING LLC",
    "email":          "Michael@MegaTruckingLLC.com",
    "confirm_email":  "Michael@MegaTruckingLLC.com",
    "phone_type":     "Business Phone",
    "phone_number":   "(786) 930-4305",
}

PAYMENT_TYPE = "Credit Card"
BODY_STYLE = "Tanker"


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


def _fill_by_label(page: Page, label_text: str, value: str, exact: bool = True) -> None:
    if not value:
        return
    try:
        page.get_by_label(label_text, exact=exact).fill(value)
        print(f'  [FILL] "{label_text}": "{value}"')
    except Exception as e:
        print(f'  [WARN] Could not fill "{label_text}": {e}')


def _select_by_label(page: Page, label_text: str, value: str) -> None:
    """
    Select a dropdown option by label. Tries exact match first, then
    case-insensitive partial match against all available options.
    """
    if not value:
        return
    try:
        loc = page.get_by_label(label_text, exact=False)
        # Read all available options so we can match flexibly
        options = loc.evaluate(
            "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
        )
        option_texts = [o["text"] for o in options]

        # 1. Try exact label match
        for o in options:
            if o["text"] == value:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] "{label_text}": "{value}" (exact)')
                return

        # 2. Try case-insensitive match
        val_lower = value.lower()
        for o in options:
            if o["text"].lower() == val_lower:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] "{label_text}": "{o["text"]}" (case-insensitive)')
                return

        # 3. Try partial/contains match (value contained in option or vice versa)
        for o in options:
            if val_lower in o["text"].lower() or o["text"].lower() in val_lower:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] "{label_text}": "{o["text"]}" (partial match for "{value}")')
                return

        # Nothing matched — log available options for debugging
        print(f'  [WARN] No match for "{label_text}" = "{value}". Available options:')
        for o in option_texts[:20]:
            print(f'    - {o!r}')

    except Exception as e:
        print(f'  [WARN] Could not select "{label_text}": {e}')


def _click_next(page: Page) -> None:
    """Click the Next button to advance to the next step."""
    selectors = [
        "button:has-text('Next')",
        "input[value='Next']",
        "a:has-text('Next')",
        "button[type='submit']",
        "input[type='submit']",
    ]
    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f"  [CLICK] Next via {sel}")
            _wait_for_page_settle(page)
            return
        except Exception:
            continue
    raise Exception("Could not find Next button")


def debug_fields(page: Page) -> None:
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
# Step functions
# ---------------------------------------------------------------------------

def step_navigate(page: Page) -> None:
    """Step 1 — Navigate to MyDMV, click Permits & Renewals, then Buy Trip Permit."""
    print("\n[STEP 1] Navigating to Arkansas DFA MyDMV portal...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _wait_for_page_settle(page)

    # Scroll down to reveal the "Permits & Renewals" filter checkbox
    page.evaluate("window.scrollBy(0, 600)")
    page.wait_for_timeout(1000)

    # Click "Permits & Renewals" filter
    permits_selectors = [
        'text=Permits & Renewals',
        'label:has-text("Permits & Renewals")',
        'a:has-text("Permits & Renewals")',
    ]
    clicked = False
    for sel in permits_selectors:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Permits & Renewals via {sel}')
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        raise Exception("Could not find 'Permits & Renewals' filter")

    _wait_for_page_settle(page)

    # Now click "Buy Trip Permit" link
    buy_selectors = [
        'a:has-text("Buy Trip Permit")',
        'text=Buy Trip Permit',
        'a:has-text("Trip Permit")',
    ]
    clicked = False
    for sel in buy_selectors:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Buy Trip Permit via {sel}')
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        raise Exception("Could not find 'Buy Trip Permit' link")

    _wait_for_page_settle(page)
    print("[OK] Trip Permit page loaded")


def _select_by_id(page: Page, field_id: str, value: str, field_name: str) -> None:
    """Select a dropdown option by element ID with fuzzy matching."""
    if not value:
        print(f'  [SKIP] {field_name}: empty value')
        return
    try:
        loc = page.locator(f"#{field_id}")
        options = loc.evaluate(
            "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
        )
        val_lower = value.lower()

        # 1. Exact match
        for o in options:
            if o["text"] == value:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] {field_name}: "{value}" (exact)')
                return

        # 2. Case-insensitive match
        for o in options:
            if o["text"].lower() == val_lower:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] {field_name}: "{o["text"]}" (case-insensitive)')
                return

        # 3. Partial/contains match
        for o in options:
            if val_lower in o["text"].lower() or o["text"].lower() in val_lower:
                loc.select_option(value=o["value"])
                print(f'  [SELECT] {field_name}: "{o["text"]}" (partial match for "{value}")')
                return

        print(f'  [WARN] No match for {field_name} = "{value}". Available:')
        for o in [opt["text"] for opt in options][:20]:
            print(f'    - {o!r}')

    except Exception as e:
        print(f'  [WARN] Could not select {field_name}: {e}')


def _fill_by_id(page: Page, field_id: str, value: str, field_name: str) -> None:
    """Fill a text input by element ID."""
    if not value:
        print(f'  [SKIP] {field_name}: empty value')
        return
    try:
        loc = page.locator(f"#{field_id}")
        loc.click(click_count=3)
        loc.fill(value)
        print(f'  [FILL] {field_name}: "{value}"')
    except Exception as e:
        print(f'  [WARN] Could not fill {field_name}: {e}')


def step_vehicle_details(page: Page, year: str, make: str, model: str,
                         tag_state: str, tag_number: str) -> None:
    """Step 2 — Fill vehicle details."""
    print("\n[STEP 2] Filling Vehicle Details...")
    debug_fields(page)

    # Use label-based for unique fields, ID-based to disambiguate
    # IDs from portal: Year=Dn-5, BodyStyle=Dn-6, Make=Dn-7, Model=Dn-8,
    # State(vehicle)=Dn-9, LicensePlate=Dn-a
    _fill_by_label(page, "Year", year)
    _select_by_label(page, "Body Style", BODY_STYLE)
    _select_by_label(page, "Make", make)
    _fill_by_label(page, "Model", model)

    # "State" is ambiguous (vehicle vs address) — use the first one on the page
    # which is the vehicle registration state
    try:
        state_selects = page.locator("select").all()
        for sel in state_selects:
            label_id = sel.get_attribute("id") or ""
            label_el = page.query_selector(f"label[for='{label_id}']")
            label_text = label_el.inner_text().strip() if label_el else ""
            if label_text == "State":
                options = sel.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                val_lower = tag_state.lower()
                for o in options:
                    if o["text"].lower() == val_lower or val_lower in o["text"].lower():
                        sel.select_option(value=o["value"])
                        print(f'  [SELECT] State (vehicle): "{o["text"]}"')
                        break
                else:
                    print(f'  [WARN] No match for vehicle State = "{tag_state}". Available:')
                    for o in [opt["text"] for opt in options][:10]:
                        print(f'    - {o!r}')
                break
    except Exception as e:
        print(f'  [WARN] Could not select vehicle State: {e}')

    _fill_by_label(page, "License Plate Number", tag_number)

    print("[OK] Vehicle Details complete")


def step_dates_and_fees(page: Page, effective_date: str) -> None:
    """Step 3 — Fill start date. Expiry and fee are auto-calculated."""
    print("\n[STEP 3] Filling Dates and Fees...")

    date_formatted = _iso_to_mmddyyyy(effective_date)
    _fill_by_label(page, "Start", date_formatted)

    print("[OK] Dates and Fees complete")


def step_address(page: Page) -> None:
    """Step 4 — Fill address with hardcoded Mega Trucking address, click Next."""
    print("\n[STEP 4] Filling Address...")

    _fill_by_label(page, "Street", ADDRESS["street"])
    _select_by_label(page, "Unit Type", ADDRESS["unit_type"])
    _fill_by_label(page, "Unit", ADDRESS["unit"])
    _fill_by_label(page, "City", ADDRESS["city"])

    # "State" is ambiguous — target the SECOND State dropdown (address state)
    try:
        state_selects = page.locator("select").all()
        state_count = 0
        for sel in state_selects:
            label_id = sel.get_attribute("id") or ""
            label_el = page.query_selector(f"label[for='{label_id}']")
            label_text = label_el.inner_text().strip() if label_el else ""
            if label_text == "State":
                state_count += 1
                if state_count == 2:  # second State = address state
                    options = sel.evaluate(
                        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                    )
                    target = ADDRESS["state"]
                    val_lower = target.lower()
                    for o in options:
                        if o["text"].lower() == val_lower or val_lower in o["text"].lower():
                            sel.select_option(value=o["value"])
                            print(f'  [SELECT] State (address): "{o["text"]}"')
                            break
                    else:
                        print(f'  [WARN] No match for address State = "{target}"')
                    break
    except Exception as e:
        print(f'  [WARN] Could not select address State: {e}')

    _fill_by_label(page, "Zip", ADDRESS["zip"])

    _click_next(page)
    print("[OK] Address complete")


def step_verify_address(page: Page) -> None:
    """Step 5 — Select 'Use Suggested Address' and click Next."""
    print("\n[STEP 5] Verifying Address...")
    debug_fields(page)

    # Select "Use Suggested Address" radio button
    suggested_selectors = [
        'input[type="radio"][value*="Suggested"]',
        'label:has-text("Use Suggested Address") input[type="radio"]',
    ]
    selected = False
    for sel in suggested_selectors:
        try:
            page.locator(sel).first.check(timeout=5_000)
            print('  [SELECT] "Use Suggested Address" radio')
            selected = True
            break
        except Exception:
            continue

    if not selected:
        # Try clicking the label text directly
        try:
            page.get_by_label("Use Suggested Address", exact=False).check()
            print('  [SELECT] "Use Suggested Address" via label')
            selected = True
        except Exception:
            # Try clicking text
            try:
                page.locator('text=Use Suggested Address').first.click(timeout=5_000)
                print('  [CLICK] "Use Suggested Address" text')
                selected = True
            except Exception:
                print("  [WARN] Could not select 'Use Suggested Address' — proceeding anyway")

    _click_next(page)
    print("[OK] Address verified")


def step_contact_info(page: Page) -> None:
    """Step 6 — Fill contact information and click Next."""
    print("\n[STEP 6] Filling Contact Information...")

    # Wait for the contact form to load
    try:
        page.get_by_label("Full Name", exact=True).wait_for(state="visible", timeout=10_000)
    except Exception:
        page.wait_for_timeout(3000)

    debug_fields(page)

    # This page has TWO sets of contact fields (non-required + required).
    # "Full Name" is unique, but Email/Phone labels are duplicated.
    # Target the required fields (second set) using get_by_role with exact names.
    _fill_by_label(page, "Full Name", CONTACT["full_name"])

    try:
        page.get_by_role("textbox", name="Email *", exact=True).fill(CONTACT["email"])
        print(f'  [FILL] Email: "{CONTACT["email"]}"')
    except Exception as e:
        print(f'  [WARN] Could not fill Email: {e}')

    try:
        page.get_by_role("textbox", name="Confirm Email *", exact=True).fill(CONTACT["confirm_email"])
        print(f'  [FILL] Confirm Email: "{CONTACT["confirm_email"]}"')
    except Exception as e:
        print(f'  [WARN] Could not fill Confirm Email: {e}')

    # Phone Type — target the second (required) dropdown
    try:
        phone_type_selects = page.get_by_label("Phone Type", exact=True).all()
        if len(phone_type_selects) >= 2:
            phone_type_selects[1].select_option(label=CONTACT["phone_type"])
        else:
            phone_type_selects[0].select_option(label=CONTACT["phone_type"])
        print(f'  [SELECT] Phone Type: "{CONTACT["phone_type"]}"')
    except Exception as e:
        print(f'  [WARN] Could not select Phone Type: {e}')

    # Phone Number — target the second (required) field
    try:
        phone_fields = page.get_by_label("Phone Number", exact=True).all()
        target = phone_fields[1] if len(phone_fields) >= 2 else phone_fields[0]
        target.fill(CONTACT["phone_number"])
        print(f'  [FILL] Phone Number: "{CONTACT["phone_number"]}"')
    except Exception as e:
        print(f'  [WARN] Could not fill Phone Number: {e}')

    _click_next(page)
    print("[OK] Contact Information complete")


def step_payment_method(page: Page) -> None:
    """Step 7 — Select Credit Card payment type and click Next. STOP after."""
    print("\n[STEP 7] Selecting Payment Method...")
    debug_fields(page)

    _select_by_label(page, "Payment Type", PAYMENT_TYPE)

    _click_next(page)

    print("[STOP] =============================================")
    print("[STOP] Payment Method submitted — NOT proceeding")
    print("[STOP] to payment confirmation. Human takes over.")
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
    Run the Arkansas trip permit automation for one driver.

    Args:
        permit:           Enriched permit dict from the backend.
        job_id:           The parent job ID (for screenshots/logging).
        on_captcha_needed: Not used — no CAPTCHA on this portal.
        company:          Company constants dict (not used — address/contact
                          are hardcoded in this module).

    Returns:
        Result dict with "status", "permitId", "driverName", etc.
    """
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")

    year = str(driver.get("year", ""))
    make = driver.get("make", "")
    model = driver.get("model", "")
    tag_state = driver.get("tagState", "")
    tag_number = driver.get("tagNumber", "")
    effective_date = permit.get("effectiveDate", "")

    # Validate required fields
    errors = []
    if not year:
        errors.append("Missing year")
    if not make:
        errors.append("Missing make")
    if not tag_state:
        errors.append("Missing tagState")
    if not tag_number:
        errors.append("Missing tagNumber")
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

    print(f"[AR-TRIP] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[AR-TRIP] Year: {year} | Make: {make} | Model: {model} | "
          f"Tag: {tag_state} {tag_number} | Eff. Date: {effective_date}")

    _reset_screenshots(job_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            slow_mo=SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        context = browser.new_context(
            viewport=None,
        )
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            step_navigate(page)
            step_vehicle_details(page, year, make, model, tag_state, tag_number)
            step_dates_and_fees(page, effective_date)
            step_address(page)
            step_verify_address(page)
            step_contact_info(page)
            step_payment_method(page)

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Payment Method submitted — stopped before payment confirmation",
            }

        except Exception as e:
            print(f"\n[AR-TRIP] Error for {driver_name}: {e}")
            try:
                _screenshot(page, "ERROR")
            except Exception:
                pass
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
