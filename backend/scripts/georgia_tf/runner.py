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


def _click_proceed_to_payment(page: Page):
    """
    Click the Proceed button to advance to the payment page.
    Does NOT interact with anything on the payment page.
    """
    print("\n[ACT] Clicking Proceed to advance to payment page...")
    proceed_btn = page.locator(SELECTORS["add_to_cart"]["proceed"]).first
    proceed_btn.wait_for(state="visible", timeout=10_000)
    proceed_btn.click()

    # Wait for payment page to load (URL change or new content)
    page.wait_for_load_state("networkidle", timeout=15_000)
    time.sleep(2)  # Brief pause to let the payment page fully render

    print("[STOP] =============================================")
    print("[STOP] Payment page reached — NOT entering payment.")
    print("[STOP] =============================================\n")


def _fill_one_permit_form(page: Page, data: dict) -> None:
    """Fill one complete permit form (all sections), stop at payment page."""
    _navigate_to_generate_trip_permit(page)
    _enter_account_number(page, data["account_no"])
    _fill_permit_details(page, data)
    _fill_motor_carrier(page, data)
    _fill_vehicle_details(page, data)
    _fill_insurance_details(page, data)
    _fill_operator_details(page)
    _click_proceed_to_payment(page)


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
        message = f"All {total} form(s) filled successfully — stopped before payment"
    elif succeeded > 0:
        status = "success"
        message = f"{succeeded}/{total} form(s) filled — {total - succeeded} failed"
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
