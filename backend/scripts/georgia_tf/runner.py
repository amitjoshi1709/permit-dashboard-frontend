"""
Georgia DMV Portal — Trip & Fuel Permit Automation

Ported from the Node.js fill_permit.js + job-queue.js.
Called by the Celery task with a permit dict from the backend.

Key differences from Alabama:
  - Requires login (GA_PORTAL_USERNAME / GA_PORTAL_PASSWORD)
  - Uses account number entry to reach the permit form
  - trip_fuel = TWO separate form submissions (ITP + MFTP)
  - Has strict safety checks before clicking Proceed

Data flow:
  Backend builds permit dict (driver details from Supabase)
  → transforms.py converts it to portal-ready field dicts
  → Runner logs in, fills form(s), stops before payment
"""

import os
import time
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from .transforms import (
    validate_permit,
    transform_permit,
    normalize_date,
    MAKE_DISPLAY_MAP,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = (
    "https://cmv.dor.ga.gov/GAEnterprise/Login/ProcessRequest/Login"
    "?ReturnUrl=%2fGAEnterprise%2fGeneral%2fProcessRequest%2fDefault"
)
SLOW_MO = 50
TIMEOUT = 30_000

# Exact selectors from debug dump of live portal (2026-03-12)
SELECTORS = {
    "login": {
        "username":     'input[name="UserName"], input[id="UserName"]',
        "password":     'input[name="Password"], input[id="Password"], input[type="password"]',
        "submit":       'input[value="Sign On"], input[type="submit"]',
    },
    "account_entry": {
        "account_no":       'input[name="AccountNo"], input[id="AccountNo"]',
        "create_permit":    'input[value="Create Permit"]',
    },
    "permit_details": {
        "permit_type":      "select#PermitType",
        # ITP uses #PermitEffDateTime, MFTP uses #PermitEffDate — try both
        "permit_eff_date":  "input#PermitEffDateTime, input#PermitEffDate",
        "permit_issue_date":"input#PermitIssueDate",
        "permit_exp_date":  "input#PermitExpDate",
        "permit_fee":       "input#PermitFee",
    },
    "motor_carrier": {
        "safety_usdot":     "input#SafetyUSDOT",
        "carrier_name":     "input#CarrierName",
    },
    "vehicle_details": {
        "vin":              "input#VIN",
        "confirmed_vin":    "input#ConfirmedVIN",
        "year":             "input#Year",
        "make":             "select#Make",
        "state_of_reg":     "select#StateOfRegistration",
        "unladen_weight":   'input#UnladenWeight, input[name="UnladenWeight"]',
    },
    "insurance_details": {
        "company":          "input#InsCompanyName",
        "eff_date":         "input#InsEffectiveDate",
        "exp_date":         "input#InsExpiryDate",
        "policy_no":        "input#InsPolicyNo",
    },
    "operator_details": {
        "usdot_radio":      'input[type="radio"][name="IsUSDOT"][value="USDOT"]',
    },
    "add_to_cart": {
        "proceed":          'input[value="Proceed"]',
        "add":              'input[value="Add to Cart"]',
    },
}

# Backward-compat make code map (if raw codes come through instead of names)
MAKE_DROPDOWN_MAP = {
    "MACK":          "MACK - Mack",
    "PETE":          "PETE - Peterbilt",
    "FRHT":          "FRHT - Freightliner",
    "KW":            "KW - Kenworth",
    "IHC":           "IHC - International",
    "INTERNATIONAL": "IHC - International",
    "VOLV":          "VOLV - Volvo",
    "INTL":          "IHC - International",
}


# ---------------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------------

class PermitError(Exception):
    pass


# ---------------------------------------------------------------------------
# Low-level helpers (ported from fill_permit.js)
# ---------------------------------------------------------------------------

def _fatal(page: Page, message: str):
    """Log fatal error and raise PermitError."""
    print(f"\n  [FATAL] {message}")
    raise PermitError(message)


def _safe_fill(page: Page, selector: str, value: str, field_name: str):
    """Fill a text input with verification."""
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Selector not found for "{field_name}": {selector}')

    locator.click(click_count=3)
    locator.fill(value)
    actual = locator.input_value()
    if actual != value:
        _fatal(page, f'Value mismatch on "{field_name}". Expected: "{value}", Got: "{actual}"')
    print(f'  [FILL] {field_name}: "{value}" \u2713')


def _safe_select(page: Page, selector: str, value: str, field_name: str):
    """Select a dropdown option by label. Reads available options first,
    then matches exact → prefix → substring (no wasted waits on missing labels)."""
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Dropdown selector not found for "{field_name}": {selector}')

    # Read all options up front so we can match flexibly without waiting.
    options = locator.evaluate(
        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
    )

    # 1. Exact label match
    for o in options:
        if o["text"] == value:
            locator.select_option(value=o["value"])
            print(f'  [SELECT] {field_name}: "{value}" \u2713')
            return

    # 2. Prefix match (e.g., "MFTP" matches "MFTP - MFTP PERMIT")
    prefix = value.split(" - ")[0].strip() if " - " in value else value.strip()
    for o in options:
        if o["text"].startswith(prefix + " ") or o["text"].startswith(prefix + "-") or o["text"] == prefix:
            locator.select_option(value=o["value"])
            print(f'  [SELECT] {field_name}: "{o["text"]}" (matched prefix "{prefix}") \u2713')
            return

    # 3. Substring match
    for o in options:
        if value.lower() in o["text"].lower() or o["text"].lower() in value.lower():
            locator.select_option(value=o["value"])
            print(f'  [SELECT] {field_name}: "{o["text"]}" (contains match) \u2713')
            return

    # Nothing matched — log all options
    print(f'  [FATAL] No match for {field_name} = "{value}". Available options:')
    for o in options:
        print(f'    - {o["text"]!r}')
    _fatal(page, f'Dropdown option not found for "{field_name}". Looking for: "{value}"')


def _wait_for_autofill(page: Page, selector: str, field_name: str, timeout: int = 10000) -> str:
    """Wait for an auto-populated field to have a non-empty value."""
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Auto-fill field not found "{field_name}": {selector}')

    start = time.time()
    while (time.time() - start) * 1000 < timeout:
        val = locator.input_value()
        if val and val.strip():
            return val
        time.sleep(0.3)
    _fatal(page, f'Auto-fill did not complete for "{field_name}" within {timeout}ms')


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _is_logged_in(page: Page) -> bool:
    """Check if we're still logged in."""
    if "/Login" in page.url:
        return False
    count = page.locator("a").filter(has_text="PERMIT").count()
    return count > 0


def _login(page: Page, username: str, password: str):
    """Log into the Georgia portal."""
    print("\n[ACT] Logging in...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")

    _safe_fill(page, SELECTORS["login"]["username"], username, "User ID")
    _safe_fill(page, SELECTORS["login"]["password"], password, "Password")

    sign_on = page.locator(SELECTORS["login"]["submit"]).first
    sign_on.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(2000)

    if "/Login" in page.url:
        _fatal(page, "Login failed — still on login page after sign-on. Check credentials.")

    print("[OK] Login successful")


# ---------------------------------------------------------------------------
# Form section functions (ported from fill_permit.js)
# ---------------------------------------------------------------------------

def _navigate_to_generate_trip_permit(page: Page):
    print("\n[ACT] Navigating to Generate Trip Permit...")

    permit_menu = page.get_by_role("link", name="PERMIT", exact=True)
    try:
        permit_menu.hover(timeout=5000)
        print("  [OK] Hovered PERMIT menu")
    except Exception as e:
        _fatal(page, f"Could not hover PERMIT menu: {e}")

    page.wait_for_timeout(500)

    gen_trip = page.get_by_role("link", name="GENERATE TRIP PERMIT", exact=True)
    try:
        gen_trip.click(timeout=5000)
        print("  [OK] Clicked GENERATE TRIP PERMIT")
    except Exception as e:
        _fatal(page, f"Could not click GENERATE TRIP PERMIT: {e}")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)

    try:
        page.wait_for_selector(SELECTORS["account_entry"]["account_no"], timeout=10000)
    except PlaywrightTimeoutError:
        _fatal(page, "Generate Trip Permit page did not load (account number field not found)")

    print("[OK] Navigated to Generate Trip Permit")


def _enter_account_number(page: Page, account_no: str):
    print(f"\n[ACT] Entering account number: {account_no}")

    acct_input = page.locator(SELECTORS["account_entry"]["account_no"]).first
    current_value = ""
    try:
        current_value = acct_input.input_value()
    except Exception:
        pass

    if current_value.strip() == account_no:
        print(f'  [OK] Account No. already pre-filled: "{account_no}"')
    else:
        _safe_fill(page, SELECTORS["account_entry"]["account_no"], account_no, "Account No.")

    try:
        create_btn = page.locator(SELECTORS["account_entry"]["create_permit"]).first
        create_btn.wait_for(timeout=5000)
        create_btn.click()
    except Exception:
        _fatal(page, '"Create Permit" button not found on account entry page')

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)

    try:
        page.wait_for_selector("select#PermitType", timeout=10000)
    except PlaywrightTimeoutError:
        _fatal(page, '"Create Permit" clicked but permit form did not load (PermitType dropdown missing)')

    print("[OK] Permit form loaded")


def _fill_permit_details(page: Page, data: dict):
    print("\n[ACT] Filling Permit Details...")

    _safe_select(page, SELECTORS["permit_details"]["permit_type"], data["permit_type"], "Permit Type")

    # Dismiss any calendar popup
    page.keyboard.press("Escape")
    page.wait_for_timeout(2000)  # let the form re-render for the selected type

    # Debug: dump visible fields after permit type is selected — helps us see
    # if MFTP uses different field IDs than ITP
    try:
        print("  [DEBUG] Visible fields after permit type selection:")
        field_info = page.evaluate("""
            () => Array.from(document.querySelectorAll('input:not([type=hidden]), select, textarea'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({id: el.id, name: el.name, type: el.type, placeholder: el.placeholder || ''}))
        """)
        for f in field_info[:30]:
            print(f"    id={f['id']!r:30s} name={f['name']!r:30s} type={f['type']!r}")
    except Exception as e:
        print(f"  [DEBUG] Could not dump fields: {e}")

    # ITP uses PermitEffDateTime (with time), MFTP uses PermitEffDate (date only)
    date_field = page.locator(SELECTORS["permit_details"]["permit_eff_date"]).first
    try:
        date_field.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        _fatal(page, f'Permit Eff. Date field not visible after selecting "{data["permit_type"]}". See DEBUG output above for actual fields on page.')

    # Determine if this is the datetime variant (ITP) or date-only (MFTP)
    field_id = date_field.evaluate("el => el.id")
    is_datetime = field_id == "PermitEffDateTime"

    auto_filled = date_field.input_value()
    desired_date = normalize_date(data["permit_eff_date"])

    if is_datetime:
        # Convert 24h time (e.g., "14:30") to portal format "HH:MM:SS AM/PM"
        raw_time = data.get("permit_eff_time", "12:00")
        try:
            h, m = [int(x) for x in raw_time.split(":")]
            period = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            portal_time = f"{str(h12).zfill(2)}:{str(m).zfill(2)}:00 {period}"
        except Exception:
            portal_time = "12:00:00 AM"
        desired_value = f"{desired_date} {portal_time}"
    else:
        desired_value = desired_date

    print(f'  [AUTO] Permit Eff. Date ({field_id}) auto-filled: "{auto_filled}"')
    print(f'  [INFO] Desired value: "{desired_value}"')

    if auto_filled == desired_value:
        print(f'  [OK] Permit Eff. Date already matches: "{desired_value}" \u2713')
    else:
        print(f'  [WARN] Value mismatch: want "{desired_value}", got "{auto_filled}". Updating...')
        date_field.click(click_count=3)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        date_field.click(click_count=3)
        page.keyboard.type(desired_value, delay=50)
        date_field.press("Tab")
        page.wait_for_timeout(500)
        new_val = date_field.input_value()
        print(f'  [FILL] Permit Eff. Date updated to: "{new_val}" \u2713')

    page.wait_for_timeout(2000)

    # Read auto-filled fields for logging
    try:
        issue = page.locator(SELECTORS["permit_details"]["permit_issue_date"]).first.input_value()
        exp = page.locator(SELECTORS["permit_details"]["permit_exp_date"]).first.input_value()
        fee = page.locator(SELECTORS["permit_details"]["permit_fee"]).first.input_value()
        print(f'  [AUTO] Permit Issue Date: "{issue}"')
        print(f'  [AUTO] Permit Exp. Date:  "{exp}"')
        print(f'  [AUTO] Permit Fee:        "{fee}"')
    except Exception:
        print("  [AUTO] Could not read auto-filled fields (may not be visible yet)")

    print("[VERIFY] Permit Details section complete")


def _fill_motor_carrier(page: Page, data: dict):
    print("\n[ACT] Filling Motor Carrier / Safety...")

    usdot_sel = SELECTORS["motor_carrier"]["safety_usdot"]
    try:
        page.wait_for_selector(usdot_sel, timeout=5000)
    except PlaywrightTimeoutError:
        _fatal(page, f"Safety USDOT field not found: {usdot_sel}")

    locator = page.locator(usdot_sel).first
    locator.click(click_count=3)
    locator.fill(data["safety_usdot"])
    locator.press("Tab")

    print("  [WAIT] Waiting for Motor Carrier auto-populate...")
    carrier_name = _wait_for_autofill(page, SELECTORS["motor_carrier"]["carrier_name"], "Carrier Name")
    print(f'  [AUTO] Carrier Name: "{carrier_name}"')

    page.wait_for_timeout(1000)
    print("[VERIFY] Motor Carrier section complete")


def _fill_vehicle_details(page: Page, data: dict):
    print("\n[ACT] Filling Vehicle Details...")

    # data["make"] is already the portal dropdown value from transforms.
    # Fall back to MAKE_DROPDOWN_MAP for backward compat with raw codes.
    make_value = data["make"]
    if data["make"] in MAKE_DROPDOWN_MAP:
        make_value = MAKE_DROPDOWN_MAP[data["make"]]

    _safe_fill(page, SELECTORS["vehicle_details"]["vin"],           data["vin"],                    "VIN")
    _safe_fill(page, SELECTORS["vehicle_details"]["confirmed_vin"], data["confirmed_vin"],           "Confirmed VIN")
    _safe_fill(page, SELECTORS["vehicle_details"]["year"],          data["year"],                    "Year")
    _safe_select(page, SELECTORS["vehicle_details"]["make"],        make_value,                      "Make")
    _safe_select(page, SELECTORS["vehicle_details"]["state_of_reg"],data["state_of_registration"],   "State of Registration")
    _safe_fill(page, SELECTORS["vehicle_details"]["unladen_weight"],data["unladen_weight"],          "Unladen Weight")

    print("[VERIFY] Vehicle Details section complete")


def _fill_insurance_details(page: Page, data: dict):
    print("\n[ACT] Filling Insurance Details...")

    _safe_fill(page, SELECTORS["insurance_details"]["company"],   data["insurance_company"],                  "Insurance Company")
    _safe_fill(page, SELECTORS["insurance_details"]["eff_date"],  normalize_date(data["insurance_eff_date"]), "Insurance Eff. Date")
    _safe_fill(page, SELECTORS["insurance_details"]["exp_date"],  normalize_date(data["insurance_exp_date"]), "Insurance Exp. Date")
    _safe_fill(page, SELECTORS["insurance_details"]["policy_no"], data["policy_no"],                          "Policy No.")

    print("[VERIFY] Insurance Details section complete")


def _fill_operator_details(page: Page):
    print("\n[ACT] Filling Operator Details (USDOT radio button only)...")

    radio_locator = None
    try:
        page.wait_for_selector(SELECTORS["operator_details"]["usdot_radio"], timeout=5000)
        radio_locator = page.locator(SELECTORS["operator_details"]["usdot_radio"]).first
    except PlaywrightTimeoutError:
        try:
            radio_locator = page.get_by_label("USDOT").first
            radio_locator.wait_for(timeout=5000)
        except Exception:
            _fatal(page, "USDOT radio button not found in Operator Details section")

    if radio_locator.is_checked():
        print("  [OK] USDOT radio button already selected (default) \u2713")
    else:
        radio_locator.click()
        if not radio_locator.is_checked():
            _fatal(page, "USDOT radio button was clicked but is not checked")
        print("  [SELECT] USDOT radio button clicked \u2713")

    print("[VERIFY] Operator Details section complete")


def _click_proceed_then_add_to_cart(page: Page):
    """Click Proceed to go to the review/cart page, then click Add to Cart."""
    # Auto-accept any JS dialogs that Proceed might trigger
    page.on("dialog", lambda dialog: dialog.accept())

    # Step 1: Click Proceed
    print("\n[ACT] Clicking Proceed...")
    proceed_btn = page.locator('#btnProceed, input[value="Proceed"]').first
    proceed_btn.wait_for(state="visible", timeout=10_000)
    proceed_btn.click()
    print("[OK] Proceed clicked")

    page.wait_for_load_state("networkidle", timeout=15_000)
    time.sleep(3)

    # Check what page we're on now
    print(f"  [INFO] URL after Proceed: {page.url}")

    # Step 2: Look for Add to Cart on the new page
    print("\n[ACT] Looking for Add to Cart...")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)

    # Debug: dump all visible buttons so we can see what's available
    print("  [DEBUG] Visible buttons:")
    for tag_sel in ['input[type="submit"]', 'input[type="button"]', "button", "a"]:
        for el in page.locator(tag_sel).all():
            try:
                if not el.is_visible():
                    continue
                val = el.get_attribute("value") or ""
                text = ""
                try:
                    text = el.inner_text().strip()[:40]
                except Exception:
                    pass
                id_ = el.get_attribute("id") or ""
                if val or text:
                    print(f"    val={val!r:25s} text={text!r:25s} id={id_!r}")
            except Exception:
                pass

    for sel in [
        'input[value="Add to Cart"]',
        'input[value="Add To Cart"]',
        'input[value="ADD TO CART"]',
        'button:has-text("Add to Cart")',
        'a:has-text("Add to Cart")',
        'input[value*="Cart" i]',
        'button:has-text("Cart")',
        '#btnAddToCart',
        'input[value*="Add" i]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                loc.click()
                print(f'  [CLICK] Add to Cart via {sel}')
                page.wait_for_load_state("networkidle", timeout=15_000)
                time.sleep(2)
                print("[OK] Added to cart")
                return
        except Exception:
            continue

    _fatal(page, "Could not find Add to Cart button — check debug dump above")


def _fill_one_permit_form(page: Page, data: dict) -> None:
    """Fill one complete permit form (all sections) and add to cart."""
    _navigate_to_generate_trip_permit(page)
    _enter_account_number(page, data["account_no"])
    _fill_permit_details(page, data)
    _fill_motor_carrier(page, data)
    _fill_vehicle_details(page, data)
    _fill_insurance_details(page, data)
    _fill_operator_details(page)
    _click_proceed_then_add_to_cart(page)


# ---------------------------------------------------------------------------
# Payment flow (Georgia portal → popup checkout)
# ---------------------------------------------------------------------------

def _wait_ga(page: Page, ms: int = 1500) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(ms / 1000)


def _fill_payment_field(frame, selectors: list[str], value: str, label: str) -> bool:
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if loc.is_visible(timeout=1_000):
                loc.click(click_count=3)
                loc.fill(value)
                print(f'  [FILL] {label}: "{value}" via {sel}')
                return True
        except Exception:
            continue
    print(f'  [MISS] Could not fill {label}')
    return False


def _select_payment_field(frame, selectors: list[str], value: str, label: str) -> bool:
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if loc.is_visible(timeout=1_000):
                opts = loc.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                val_lower = value.lower()
                for o in opts:
                    if o["value"] == value or o["text"] == value:
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] {label}: "{o["text"]}" via {sel}')
                        return True
                for o in opts:
                    if val_lower in o["value"].lower() or val_lower in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] {label}: "{o["text"]}" (fuzzy) via {sel}')
                        return True
        except Exception:
            continue
    print(f'  [MISS] Could not select {label}')
    return False


def step_navigate_to_cart_payment(page: Page):
    """Navigate to Payment → Cart Payment using the same hover-menu pattern as PERMIT."""
    print("\n[PAYMENT 1] Navigating to PAYMENT → CART PAYMENT...")

    # Hover the PAYMENT menu item (same pattern as PERMIT menu)
    payment_menu = page.get_by_role("link", name="PAYMENT", exact=True)
    try:
        payment_menu.hover(timeout=5000)
        print("  [OK] Hovered PAYMENT menu")
    except Exception:
        # Try case variations
        for name in ["Payment", "PAYMENT", "payment"]:
            try:
                loc = page.get_by_role("link", name=name)
                loc.hover(timeout=3000)
                print(f'  [OK] Hovered menu via name="{name}"')
                break
            except Exception:
                continue
        else:
            _fatal(page, "Could not find PAYMENT menu in toolbar")

    page.wait_for_timeout(500)

    # Click CART PAYMENT from the dropdown
    for name in ["CART PAYMENT", "Cart Payment", "CART PAYMENTS"]:
        try:
            loc = page.get_by_role("link", name=name)
            loc.click(timeout=3000)
            print(f'  [OK] Clicked {name}')
            break
        except Exception:
            continue
    else:
        # Fallback to text-based
        for sel in ['a:has-text("Cart Payment")', 'text=Cart Payment']:
            try:
                page.locator(sel).first.click(timeout=3000)
                print(f'  [OK] Clicked Cart Payment via {sel}')
                break
            except Exception:
                continue
        else:
            _fatal(page, "Could not find CART PAYMENT in dropdown")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    print("[OK] On Cart Payment page")


def step_click_pay(page: Page):
    """Click the Pay button at the bottom of the cart payment page."""
    print("\n[PAYMENT 2] Clicking Pay...")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)

    for sel in [
        'input[value="Pay"]', 'button:has-text("Pay")',
        'a:has-text("Pay")', 'input[type="submit"][value="Pay"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Pay via {sel}')
                break
        except Exception:
            continue
    else:
        _fatal(page, "Could not find Pay button")

    _wait_ga(page, 3000)
    print("[OK] Pay clicked")


def step_click_proceed(page: Page):
    """Click the Proceed button."""
    print("\n[PAYMENT 3] Clicking Proceed...")

    for sel in [
        'input[value="Proceed"]', 'button:has-text("Proceed")',
        'a:has-text("Proceed")', 'input[type="submit"][value="Proceed"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Proceed via {sel}')
                break
        except Exception:
            continue
    else:
        _fatal(page, "Could not find Proceed button")

    _wait_ga(page, 3000)
    print("[OK] Proceed clicked")


def step_click_pay_now(page: Page):
    """Click Pay Now — this triggers a popup window for card entry."""
    print("\n[PAYMENT 4] Clicking Pay Now...")

    for sel in [
        'input[value="Pay Now"]', 'button:has-text("Pay Now")',
        'a:has-text("Pay Now")', 'input[type="submit"][value="Pay Now"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Pay Now via {sel}')
                break
        except Exception:
            continue
    else:
        _fatal(page, "Could not find Pay Now button")

    time.sleep(3)
    print("[OK] Pay Now clicked — popup should appear")


def step_fill_card_popup(page: Page, payment_card: dict):
    """Fill credit card info in the popup window that Pay Now opens."""
    print("\n[PAYMENT 5] Filling card in popup...")

    # Wait for the popup to appear
    popup_page = None
    all_pages = page.context.pages
    for p in all_pages:
        if p != page:
            popup_page = p
            break

    if not popup_page:
        # Try waiting for it
        try:
            with page.context.expect_page(timeout=10_000) as new_page_info:
                pass
            popup_page = new_page_info.value
        except Exception:
            pass

    if not popup_page:
        _fatal(page, "Payment popup window did not appear")

    popup_page.wait_for_load_state("domcontentloaded", timeout=15_000)
    time.sleep(5)
    # Wait for the page to fully render — govhub.com takes a moment
    try:
        popup_page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(3)
    print(f"  [INFO] Popup URL: {popup_page.url[:80]}")

    # The popup may have an iframe for card fields — govhub loads them dynamically
    target = popup_page
    card_found = False
    for sel in [
        'input[name*="CardNumber" i]', 'input[id*="CardNumber" i]',
        'input[name*="ccNumber" i]', 'input[autocomplete="cc-number"]',
        'input[name*="card" i]', 'input[name*="cardnumber" i]',
        'input[id*="card" i]', 'input[placeholder*="card" i]',
    ]:
        try:
            if popup_page.locator(sel).first.is_visible(timeout=5_000):
                card_found = True
                break
        except Exception:
            continue

    if not card_found:
        for frame in popup_page.frames:
            if frame == popup_page.main_frame:
                continue
            try:
                for sel in ['input[name*="CardNumber" i]', 'input[id*="CardNumber" i]', 'input[type="tel"]']:
                    if frame.locator(sel).first.is_visible(timeout=2_000):
                        target = frame
                        card_found = True
                        print(f'  [INFO] Card fields in iframe: {frame.url[:60]}')
                        break
                if card_found:
                    break
            except Exception:
                continue

    if not card_found:
        print("  [DEBUG] Popup main page fields:")
        fields = popup_page.query_selector_all("input:not([type='hidden']), select")
        for el in fields:
            id_ = el.get_attribute("id") or ""
            name = el.get_attribute("name") or ""
            type_ = el.get_attribute("type") or ""
            ph = el.get_attribute("placeholder") or ""
            print(f"    id={id_!r:30s} name={name!r:30s} type={type_!r:12s} ph={ph!r}")
        # Check iframes
        for frame in popup_page.frames:
            if frame == popup_page.main_frame:
                continue
            print(f"  [DEBUG] Iframe: {frame.url[:80]}")
            try:
                iframe_fields = frame.query_selector_all("input:not([type='hidden']), select")
                for el in iframe_fields:
                    id_ = el.get_attribute("id") or ""
                    name = el.get_attribute("name") or ""
                    type_ = el.get_attribute("type") or ""
                    print(f"    id={id_!r:30s} name={name!r:30s} type={type_!r}")
            except Exception:
                print("    (could not read iframe fields)")

    # Always dump fields so we can see what govhub has
    print("  [DEBUG] All popup fields (main page):")
    fields = popup_page.query_selector_all("input:not([type='hidden']), select")
    for el in fields:
        id_ = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        type_ = el.get_attribute("type") or ""
        ac = el.get_attribute("autocomplete") or ""
        ph = el.get_attribute("placeholder") or ""
        print(f"    id={id_!r:25s} name={name!r:25s} type={type_!r:10s} ac={ac!r:15s} ph={ph!r}")

    # Check ALL iframes — card fields are often in a Stripe/payment iframe
    print(f"  [DEBUG] Frames: {len(popup_page.frames)}")
    for frame in popup_page.frames:
        if frame == popup_page.main_frame:
            continue
        print(f"  [DEBUG] Iframe: {frame.url[:100]}")
        try:
            iframe_fields = frame.query_selector_all("input, select")
            for el in iframe_fields:
                id_ = el.get_attribute("id") or ""
                name = el.get_attribute("name") or ""
                type_ = el.get_attribute("type") or ""
                ph = el.get_attribute("placeholder") or ""
                print(f"    id={id_!r:25s} name={name!r:25s} type={type_!r:10s} ph={ph!r}")
        except Exception as e:
            print(f"    (error reading iframe: {e})")

    # Try filling on main page first, then each iframe
    targets_to_try = [popup_page] + [f for f in popup_page.frames if f != popup_page.main_frame]

    # Govhub uses separate iframes for each card field (vault.county-taxes.com):
    #   iframe 1: #cc_credit_card_number  (type=tel)
    #   iframe 2: #cc_expiration_date     (type=tel, placeholder=mm/yy)
    #   iframe 3: #cc_cvv_number          (type=tel)
    # Name on card is on the main popup page.

    iframes = [f for f in popup_page.frames if f != popup_page.main_frame]

    # Card number — iframe 1
    for f in iframes:
        if _fill_payment_field(f, [
            '#cc_credit_card_number', 'input[autocomplete="cc-number"]',
            'input[type="tel"]',
        ], payment_card["cardNumber"], "Card Number"):
            break

    # Expiration — iframe 2 (single MM/YY input)
    exp = f"{payment_card['expMonth']}/{payment_card['expYear'][-2:]}"
    for f in iframes:
        if _fill_payment_field(f, [
            '#cc_expiration_date', 'input[placeholder*="mm" i]',
            'input[autocomplete="cc-exp"]',
        ], exp, "Expiration"):
            break

    # CVV — iframe 3
    for f in iframes:
        if _fill_payment_field(f, [
            '#cc_cvv_number', 'input[autocomplete="cc-csc"]',
        ], payment_card["cvv"], "CVV"):
            break

    # Name on card — main popup page (not in an iframe)
    _fill_payment_field(popup_page, [
        '#name-on-card-52', 'input[autocomplete="cc-name"]',
        'input[name="user-name"]',
    ], payment_card["cardholderName"], "Name on Card")

    # Billing address + contact — all on the main popup page
    _fill_payment_field(popup_page, [
        '#address-62', 'input[name="address1"]', 'input[autocomplete="address-line1"]',
    ], "5979 NW 151 ST Suite 101", "Address")

    _fill_payment_field(popup_page, [
        '#city-62', 'input[name="city"]', 'input[autocomplete="address-level2"]',
    ], "Miami Lakes", "City")

    # State dropdown
    for sel in ['#state-62', 'input[name="state"]', 'select[name="state"]']:
        try:
            loc = popup_page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    opts = loc.evaluate(
                        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                    )
                    for o in opts:
                        if "florida" in o["text"].lower() or o["value"] == "FL":
                            loc.select_option(value=o["value"])
                            print(f'  [SELECT] State: "{o["text"]}"')
                            break
                else:
                    loc.fill("FL")
                    print('  [FILL] State: "FL"')
                break
        except Exception:
            continue

    _fill_payment_field(popup_page, [
        '#postal-code-62', 'input[name="postal-code"]', 'input[autocomplete="postal-code"]',
    ], "33014", "Postal Code")

    # Country dropdown
    for sel in ['#country-62', 'input[name="country"]', 'select[name="country"]']:
        try:
            loc = popup_page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    opts = loc.evaluate(
                        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                    )
                    for o in opts:
                        if "united states" in o["text"].lower() or o["value"] == "US":
                            loc.select_option(value=o["value"])
                            print(f'  [SELECT] Country: "{o["text"]}"')
                            break
                else:
                    loc.fill("US")
                    print('  [FILL] Country: "US"')
                break
        except Exception:
            continue

    _fill_payment_field(popup_page, [
        '#email-84', 'input[name="email"]', 'input[autocomplete="email"]',
    ], "paceywells03134@gmail.com", "Email")

    _fill_payment_field(popup_page, [
        '#phone-number-84', 'input[name="phone"]', 'input[autocomplete="tel"]',
    ], "9543998833", "Phone")

    # Submit payment form on popup page
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    for sel in [
        'button:has-text("Pay")', 'input[value="Pay"]',
        'button:has-text("Submit")', 'input[value="Submit"]',
        'button:has-text("Continue")', 'input[value="Continue"]',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            loc = popup_page.locator(sel).first
            if loc.is_visible(timeout=3_000):
                loc.click()
                print(f'  [CLICK] via {sel}')
                break
        except Exception:
            continue

    time.sleep(5)

    # Final confirmation page — click Submit
    print("\n[PAYMENT 6] Final confirmation — clicking Submit...")
    popup_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    for sel in [
        'button:has-text("Submit")', 'input[value="Submit"]',
        'button:has-text("Pay")', 'input[value="Pay"]',
        'button:has-text("Confirm")', 'input[value="Confirm"]',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            loc = popup_page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Final submit via {sel}')
                break
        except Exception:
            continue

    time.sleep(5)
    print("[OK] Payment submitted")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    permit: dict,
    job_id: str,
    on_captcha_needed: Optional[Callable] = None,
    company: dict = None,
    payment_card: dict = None,
) -> dict:
    """
    Run the Georgia trip/fuel permit automation for one driver.

    Unlike Alabama (which handles trip+fuel in one form), Georgia requires
    separate form submissions for each permit type. So trip_fuel = 2 fills.

    Args:
        permit:           Enriched permit dict from the backend.
        job_id:           The parent job ID (for logging).
        on_captcha_needed: Not used for Georgia (login-based, no CAPTCHA).
                          Kept for interface compatibility with Alabama.
        company:          Company constants dict (not used for Georgia —
                          the portal auto-fills carrier info from USDOT).

    Returns:
        Result dict with "status", "permitId", and per-form results.
    """
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")

    # ── Validate ──────────────────────────────────────────────────────
    if not payment_card or not payment_card.get("cardNumber"):
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": "No payment card configured — go to Settings to add a card",
        }

    errors = validate_permit(permit)
    if errors:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": f"Validation failed: {'; '.join(errors)}",
        }

    # ── Transform to portal-ready dicts ───────────────────────────────
    # Georgia account number — hardcoded for Mega Trucking
    ga_account_no = os.getenv("GA_ACCOUNT_NO", "82761")
    try:
        portal_data_list = transform_permit(permit, account_no=ga_account_no)
    except ValueError as e:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": f"Transform failed: {e}",
        }

    # ── Credentials ───────────────────────────────────────────────────
    username = os.getenv("GA_PORTAL_USERNAME")
    password = os.getenv("GA_PORTAL_PASSWORD")
    if not username or not password:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": "Missing GA_PORTAL_USERNAME or GA_PORTAL_PASSWORD in .env",
        }

    print(f"[Georgia] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[Georgia] Will fill {len(portal_data_list)} form(s): "
          + ", ".join(d["_portalPermitType"] for d in portal_data_list))

    form_results = []

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
            # Login once
            _login(page, username, password)

            # Fill each form (1 for trip or fuel, 2 for trip_fuel)
            for i, portal_data in enumerate(portal_data_list):
                label = f"{permit_id} [{portal_data['_portalPermitType']}]"
                print(f"\n[Georgia] Filling form {i + 1}/{len(portal_data_list)}: {label}")

                # Re-login if session expired between forms
                if not _is_logged_in(page):
                    print("[WARN] Session expired — re-logging in...")
                    _login(page, username, password)

                try:
                    _fill_one_permit_form(page, portal_data)
                    form_results.append({
                        "permitType": portal_data["_portalPermitType"],
                        "status": "success",
                    })
                except PermitError as e:
                    print(f"  [FORM ERROR] {portal_data['_portalPermitType']}: {e}")
                    form_results.append({
                        "permitType": portal_data["_portalPermitType"],
                        "status": "error",
                        "message": str(e),
                    })
                except Exception as e:
                    print(f"  [FORM ERROR] {portal_data['_portalPermitType']}: Unexpected: {e}")
                    form_results.append({
                        "permitType": portal_data["_portalPermitType"],
                        "status": "error",
                        "message": f"Unexpected: {e}",
                    })

            # Payment flow — only if at least one form succeeded
            succeeded_forms = sum(1 for r in form_results if r["status"] == "success")
            if succeeded_forms > 0:
                step_navigate_to_cart_payment(page)
                step_click_pay(page)
                step_click_proceed(page)
                step_click_pay_now(page)
                step_fill_card_popup(page, payment_card)

        except PermitError as e:
            # Top-level error (login failure, etc.)
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

    # ── Build result ──────────────────────────────────────────────────
    succeeded = sum(1 for r in form_results if r["status"] == "success")
    total = len(form_results)

    if succeeded == total:
        status = "success"
        message = f"All {total} form(s) filled — payment submitted"
    elif succeeded > 0:
        status = "success"
        message = f"{succeeded}/{total} form(s) filled — payment submitted for successful ones"
    else:
        status = "error"
        message = f"All {total} form(s) failed"

    print(f"\n[Georgia] {permit_id}: {message}")

    return {
        "permitId": permit_id,
        "driverName": driver_name,
        "tractor": tractor,
        "permitType": permit_type,
        "status": status,
        "message": message,
        "formResults": form_results,
    }


def run_batch(
    permits: list[dict],
    job_id: str,
    on_captcha_needed: Optional[Callable] = None,
    company: dict = None,
    payment_card: dict = None,
) -> list[dict]:
    """
    Process multiple GA permits in one browser session.

    Fills each permit form and adds to cart, then pays for all at once.
    This avoids the 45-minute cooldown between individual purchases.

    Returns a list of result dicts (one per permit).
    """
    if not payment_card or not payment_card.get("cardNumber"):
        return [{
            "permitId": p["permitId"],
            "driverName": f"{p['driver']['firstName']} {p['driver']['lastName']}",
            "tractor": p["driver"].get("tractor", ""),
            "permitType": p.get("permitType", ""),
            "status": "error",
            "message": "No payment card configured — go to Settings to add a card",
        } for p in permits]

    username = os.getenv("GA_PORTAL_USERNAME")
    password = os.getenv("GA_PORTAL_PASSWORD")
    if not username or not password:
        return [{
            "permitId": p["permitId"],
            "driverName": f"{p['driver']['firstName']} {p['driver']['lastName']}",
            "tractor": p["driver"].get("tractor", ""),
            "permitType": p.get("permitType", ""),
            "status": "error",
            "message": "Missing GA_PORTAL_USERNAME or GA_PORTAL_PASSWORD in .env",
        } for p in permits]

    ga_account_no = os.getenv("GA_ACCOUNT_NO", "82761")

    # Pre-validate and transform all permits
    all_forms = []
    results = []
    for permit in permits:
        driver = permit["driver"]
        driver_name = f"{driver['firstName']} {driver['lastName']}"
        tractor = driver.get("tractor", "")
        permit_id = permit["permitId"]
        permit_type = permit.get("permitType", "")

        errors = validate_permit(permit)
        if errors:
            results.append({
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": f"Validation failed: {'; '.join(errors)}",
            })
            continue

        try:
            portal_data_list = transform_permit(permit, account_no=ga_account_no)
        except ValueError as e:
            results.append({
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": f"Transform failed: {e}",
            })
            continue

        for pd in portal_data_list:
            all_forms.append({
                "permit_id": permit_id,
                "driver_name": driver_name,
                "tractor": tractor,
                "permit_type": permit_type,
                "portal_data": pd,
            })

    if not all_forms:
        return results

    print(f"[Georgia BATCH] Processing {len(all_forms)} form(s) across {len(permits)} permit(s)")

    form_results = {}

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

            # Phase 1: Fill all forms and add each to cart
            for i, form in enumerate(all_forms):
                label = f"{form['permit_id']} [{form['portal_data']['_portalPermitType']}] for {form['driver_name']}"
                print(f"\n[Georgia BATCH] Adding to cart {i + 1}/{len(all_forms)}: {label}")

                if not _is_logged_in(page):
                    print("[WARN] Session expired — re-logging in...")
                    _login(page, username, password)

                try:
                    _fill_one_permit_form(page, form["portal_data"])
                    form_results.setdefault(form["permit_id"], []).append("success")
                    print(f"  [OK] Added to cart")
                except (PermitError, Exception) as e:
                    print(f"  [ERROR] {e}")
                    form_results.setdefault(form["permit_id"], []).append("error")

            # Phase 2: Pay for everything in the cart at once
            total_in_cart = sum(
                1 for statuses in form_results.values()
                for s in statuses if s == "success"
            )
            if total_in_cart > 0:
                print(f"\n[Georgia BATCH] {total_in_cart} permit(s) in cart — proceeding to payment")
                step_navigate_to_cart_payment(page)
                step_click_pay(page)
                step_click_proceed(page)
                step_click_pay_now(page)
                step_fill_card_popup(page, payment_card)
            else:
                print("\n[Georgia BATCH] No permits added to cart — skipping payment")

        except (PermitError, Exception) as e:
            print(f"\n[Georgia BATCH] Fatal error: {e}")
            # Mark all remaining permits as failed
            for permit in permits:
                pid = permit["permitId"]
                if pid not in form_results:
                    form_results[pid] = ["error"]

        finally:
            time.sleep(3)
            try:
                browser.close()
            except Exception:
                pass

    # Build per-permit results
    for permit in permits:
        pid = permit["permitId"]
        if any(r["permitId"] == pid for r in results):
            continue
        driver = permit["driver"]
        statuses = form_results.get(pid, [])
        succeeded = statuses.count("success")
        total = len(statuses)
        if total == 0:
            status, message = "error", "No forms processed"
        elif succeeded == total:
            status, message = "success", f"All {total} form(s) added to cart — payment submitted"
        elif succeeded > 0:
            status, message = "success", f"{succeeded}/{total} form(s) added to cart — payment submitted"
        else:
            status, message = "error", f"All {total} form(s) failed"
        results.append({
            "permitId": pid,
            "driverName": f"{driver['firstName']} {driver['lastName']}",
            "tractor": driver.get("tractor", ""),
            "permitType": permit.get("permitType", ""),
            "status": status,
            "message": message,
        })

    print(f"\n[Georgia BATCH] Done — {sum(1 for r in results if r['status'] == 'success')}/{len(results)} succeeded")
    return results
