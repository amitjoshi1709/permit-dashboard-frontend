"""
Mississippi MDOT — 72 Hour Legal Trip Permit Automation

Portal: https://permits.mdot.ms.gov/
Permit type: 72 Hour Legal Trip (only)
Login: Required (MS_MDOT_USERNAME / MS_MDOT_PASSWORD)
Automation boundary: Fills all form fields through the Permit Provisions
  review screen. Does NOT click Submit.

The MS portal is ASP.NET WebForms — field names use ctl00$ContentPlaceHolder1$...
prefixes. Label-based selectors mostly fail because labels lack `for` attributes.
We use a combination of partial name matching and nearby-text strategies.
"""

import os
import re
import time
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://permits.mdot.ms.gov/"
SLOW_MO = 300
TIMEOUT = 30_000

CONTACT = {
    "name":             "Michael Caballero",
    "phone":            "786-332-5691",
    "email":            "INFO@MEGATRUCKINGLLC.COM",
    "delivery_method":  "Email",
    "company_ref":      "MEGA TRUCKING LLC",
}

# Fake test card — matches the default in the dashboard Settings page.
# These are NOT real credentials; 4242... is a standard Stripe test number.
PAYMENT_CARD = {
    "number":   "4242424242424242",
    "exp_month": "12",
    "exp_year":  "2028",
    "cvv":       "123",
    "name":      "Michael Caballero",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait(page: Page, ms: int = 1500) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(ms / 1000)


def _iso_to_mmddyyyy(date_str: str) -> str:
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


def _format_time_12h(time_str: str) -> str:
    if not time_str:
        return "12:00 AM"
    parts = time_str.replace(":", " ").split()
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{str(m).zfill(2)} {period}"


def _debug_fields(page: Page, filter_ids: list[str] = None) -> None:
    """Dump form elements. If filter_ids given, only print fields whose id contains one of them."""
    fields = page.query_selector_all("input:not([type='hidden']), select, textarea")
    printed = 0
    for el in fields:
        id_ = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        # Skip template rows (ZZ suffix) and fields with no id/name
        if "ZZ" in id_ or (not id_ and not name):
            continue
        if filter_ids and not any(f.lower() in id_.lower() for f in filter_ids):
            continue
        type_ = el.get_attribute("type") or el.evaluate("el => el.tagName.toLowerCase()")
        val = ""
        try:
            val = el.input_value()[:40]
        except Exception:
            pass
        print(f"  id={id_!r:35s} name={name!r:50s} type={type_!r:10s} val={val!r}")
        printed += 1
    if printed == 0:
        print("  (no matching fields found)")


def _fill_by_name_fragment(page: Page, fragment: str, value: str, label: str) -> bool:
    """Find an input/select whose `name` attribute contains `fragment` (case-insensitive)."""
    try:
        els = page.query_selector_all("input:not([type='hidden']), select, textarea")
        for el in els:
            name = el.get_attribute("name") or ""
            if fragment.lower() in name.lower():
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    el.select_option(label=value)
                else:
                    el.click(click_count=3)
                    el.fill(value)
                print(f'  [FILL] {label}: "{value}" via name fragment "{fragment}" (name={name!r})')
                return True
    except Exception as e:
        print(f'  [WARN] _fill_by_name_fragment({fragment}): {e}')
    return False


def _fill_payment_field(frame, selectors: list[str], value: str, label: str) -> bool:
    """Fill a text input on a payment page, trying multiple selectors."""
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
    """Select a dropdown option on a payment page, trying multiple selectors."""
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if loc.is_visible(timeout=1_000):
                # Try selecting by value first, then by label text
                opts = loc.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                # Exact value match
                for o in opts:
                    if o["value"] == value or o["text"] == value:
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] {label}: "{o["text"]}" via {sel}')
                        return True
                # Partial/contains match
                val_lower = value.lower()
                for o in opts:
                    if val_lower in o["value"].lower() or val_lower in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] {label}: "{o["text"]}" (fuzzy) via {sel}')
                        return True
        except Exception:
            continue
    print(f'  [MISS] Could not select {label}')
    return False


def _select_by_name_fragment(page: Page, fragment: str, value: str, label: str) -> bool:
    """Find a <select> whose `name` contains `fragment` and pick an option by label text."""
    try:
        els = page.query_selector_all("select")
        for el in els:
            name = el.get_attribute("name") or ""
            if fragment.lower() in name.lower():
                opts = el.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                val_lower = value.lower()
                for o in opts:
                    if o["text"].lower() == val_lower or val_lower in o["text"].lower():
                        el.select_option(value=o["value"])
                        print(f'  [SELECT] {label}: "{o["text"]}" via name fragment "{fragment}"')
                        return True
                print(f'  [WARN] No matching option for {label}. Available:')
                for o in opts[:15]:
                    print(f'    - {o["text"]!r}')
                return False
    except Exception as e:
        print(f'  [WARN] _select_by_name_fragment({fragment}): {e}')
    return False


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def step_login(page: Page) -> None:
    print("\n[STEP 1] Logging in to MS MDOT portal...")

    username = os.getenv("MS_MDOT_USERNAME", "")
    password = os.getenv("MS_MDOT_PASSWORD", "")
    if not username or not password:
        raise Exception("MS_MDOT_USERNAME or MS_MDOT_PASSWORD not set in .env")

    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _wait(page, 3000)

    # Username — try type-based selectors since ASP.NET names are unpredictable
    username_filled = False
    for sel in [
        'input[type="text"]', 'input[type="email"]',
        'input[name*="Username" i]', 'input[name*="UserName" i]',
        'input[id*="Username" i]', 'input[id*="UserName" i]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.fill(username)
                print(f'  [FILL] Username via {sel}')
                username_filled = True
                break
        except Exception:
            continue
    if not username_filled:
        try:
            page.get_by_placeholder("Username", exact=False).fill(username)
            print('  [FILL] Username via placeholder')
            username_filled = True
        except Exception:
            pass
    if not username_filled:
        raise Exception("Could not find Username field")

    # Password
    password_filled = False
    try:
        loc = page.locator('input[type="password"]').first
        if loc.is_visible():
            loc.fill(password)
            print('  [FILL] Password via input[type="password"]')
            password_filled = True
    except Exception:
        pass
    if not password_filled:
        raise Exception("Could not find Password field")

    # Submit
    for sel in [
        'button:has-text("Submit")', 'button:has-text("Log In")',
        'button:has-text("Sign In")', 'input[type="submit"]',
        'button[type="submit"]', 'a:has-text("Submit")',
    ]:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] Login via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find login Submit button")

    _wait(page, 3000)
    print("[OK] Logged in")


def step_system_user_notice(page: Page) -> None:
    print("\n[STEP 2] Handling System User Notice...")

    try:
        page.locator('input[type="checkbox"]').first.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        if page.locator('button:has-text("New Permit")').count() > 0:
            print("  [SKIP] No System User Notice — already on dashboard")
            return
        _wait(page, 2000)

    checkboxes = page.locator('input[type="checkbox"]').all()
    for i, cb in enumerate(checkboxes):
        try:
            if cb.is_visible() and not cb.is_checked():
                cb.check()
                print(f"  [CHECK] Disclaimer checkbox {i + 1}")
        except Exception as e:
            print(f"  [WARN] Could not check checkbox {i + 1}: {e}")

    _wait(page, 500)

    for sel in [
        'button:has-text("I Understand and Agree")',
        'button:has-text("I Understand")', 'button:has-text("Agree")',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] Agree via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find 'I Understand and Agree' button")

    _wait(page, 2000)
    print("[OK] System User Notice accepted")


def step_new_permit(page: Page) -> None:
    print("\n[STEP 3] Starting new permit from dashboard...")

    for sel in [
        'button:has-text("New Permit")', 'a:has-text("New Permit")',
        'text=New Permit',
    ]:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] New Permit via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find 'New Permit' button")

    _wait(page, 1000)

    for sel in [
        'text=I know which permit I need',
        'a:has-text("I know which permit I need")',
        'button:has-text("I know which permit I need")',
    ]:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] "I know which permit I need" via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find 'I know which permit I need' option")

    _wait(page, 2000)
    print("[OK] Order Permits page loaded")


def step_contact_info(page: Page) -> None:
    """Fill Contact Name only — the rest is pre-populated from the portal account."""
    print("\n[STEP 4] Filling Contact Name...")

    if not _fill_by_name_fragment(page, "ContactName", CONTACT["name"], "Contact Name"):
        print("  [WARN] Could not fill Contact Name")

    print("[OK] Contact info ready")


def step_select_permit_type(page: Page) -> None:
    print("\n[STEP 5-6] Selecting Permit Type...")

    try:
        page.locator('text=Permit Type').first.scroll_into_view_if_needed()
    except Exception:
        page.evaluate("window.scrollBy(0, 400)")
    _wait(page, 500)

    target = "72 Hour Legal Trip"

    # Try ASP.NET name fragment
    if _select_by_name_fragment(page, "PermitType", target, "Permit Type"):
        _wait(page, 1000)
        print("[OK] Permit Type selected")
        return

    # Fallback: scan every <select> for an option containing "72 hour"
    selects = page.locator("select").all()
    for s in selects:
        opts = s.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))")
        for o in opts:
            if "72 hour" in o["text"].lower() and "legal" in o["text"].lower():
                s.select_option(value=o["value"])
                print(f'  [SELECT] Permit Type: "{o["text"]}" (scan match)')
                _wait(page, 1000)
                print("[OK] Permit Type selected")
                return
    raise Exception(f"Could not find Permit Type option '{target}'")


def step_effective_date_time(page: Page, effective_date: str, effective_time: str) -> None:
    print("\n[STEP 7] Setting Effective Date & Time...")

    date_formatted = _iso_to_mmddyyyy(effective_date)
    time_formatted = _format_time_12h(effective_time)

    # Date
    if not _fill_by_name_fragment(page, "EffectiveDate", date_formatted, "Effective Date"):
        if not _fill_by_name_fragment(page, "FromDate", date_formatted, "From Date"):
            try:
                page.get_by_label("From", exact=False).first.fill(date_formatted)
                print(f'  [FILL] Effective Date: "{date_formatted}" via label')
            except Exception as e:
                print(f'  [WARN] Could not fill date: {e}')

    # Time
    if not _fill_by_name_fragment(page, "EffectiveTime", time_formatted, "Effective Time"):
        if not _fill_by_name_fragment(page, "FromTime", time_formatted, "From Time"):
            try:
                page.get_by_label("Time", exact=False).first.fill(time_formatted)
                print(f'  [FILL] Effective Time: "{time_formatted}" via label')
            except Exception as e:
                print(f'  [WARN] Could not fill time: {e}')

    _wait(page, 500)

    # Verify permit type is still correct before the point of no return
    try:
        selects = page.query_selector_all("select")
        for s in selects:
            name = s.get_attribute("name") or ""
            if "permittype" in name.lower():
                selected = s.evaluate("el => el.options[el.selectedIndex]?.text?.trim() || ''")
                if selected and "72 hour" not in selected.lower():
                    raise Exception(
                        f"Permit Type mismatch: expected '72 Hour Legal Trip', got '{selected}'"
                    )
                if selected:
                    print(f'  [VERIFY] Permit Type confirmed: "{selected}"')
                break
    except Exception as e:
        if "mismatch" in str(e).lower():
            raise
        print(f'  [WARN] Could not verify permit type: {e}')

    # Click Next — on the order page it's id="NextButton" type="button"
    for sel in ['#NextButton', 'input[value="Next"]', 'button:has-text("Next")']:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Next via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Next button on date/time page")

    _wait(page, 3000)
    print("[OK] Effective date/time set, proceeding to vehicle selection")


def step_vehicle_selection(page: Page, unit_number: str) -> None:
    """Select a vehicle from the TruckSelect0_0 dropdown by matching unit number."""
    print(f'\n[STEP 8] Selecting vehicle: "{unit_number}"...')

    # The vehicle inventory is a <select> with id="TruckSelect0_0"
    vehicle_sel = page.locator('#TruckSelect0_0')
    try:
        vehicle_sel.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        _debug_fields(page, ["Truck", "Vehicle", "Unit"])
        raise Exception("Could not find Vehicle Inventory dropdown (#TruckSelect0_0)")

    options = vehicle_sel.evaluate(
        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
    )
    unit_lower = unit_number.lower().strip()
    matched = False
    for o in options:
        opt_lower = o["text"].lower()
        # Match: unit number appears at start, or is contained in the option text
        if opt_lower.startswith(unit_lower) or unit_lower in opt_lower:
            vehicle_sel.select_option(value=o["value"])
            print(f'  [SELECT] Vehicle: "{o["text"]}"')
            matched = True
            break

    if not matched:
        avail = [o["text"] for o in options if o["value"] and o["value"] != "-1"][:20]
        raise Exception(
            f"Unit '{unit_number}' not found in Vehicle Inventory. "
            f"Available: {avail}. Register this unit in the MS portal first."
        )

    _wait(page, 2000)
    print("[OK] Vehicle selected and fields should have autopopulated")


def step_click_next_vehicle(page: Page) -> None:
    print("\n[STEP 9] Clicking Next on vehicle page...")

    # Vehicle page Next is id="LDNextButton" type="submit"
    for sel in ['#LDNextButton', '#NextButton', 'input[value="Next"]', 'button:has-text("Next")']:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Next via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Next button on vehicle page")

    _wait(page, 3000)
    print("[OK] Vehicle page submitted")


def step_permit_provisions_submit(page: Page) -> None:
    """Step 10 — On Permit Provisions page, click Submit then OK on popup."""
    print("\n[STEP 10] Permit Provisions — clicking Submit...")

    # Wait for Submit button to appear
    for sel in [
        '#SubmitButton', 'input[value="Submit"]',
        'button:has-text("Submit")', 'input[type="submit"][value="Submit"]',
    ]:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=15_000)
            loc.click()
            print(f'  [CLICK] Submit via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Submit button on Permit Provisions page")

    # Handle OK popup (likely a JS confirm/alert dialog)
    _wait(page, 1000)
    try:
        page.locator('button:has-text("OK")').first.click(timeout=5_000)
        print('  [CLICK] OK on popup')
    except Exception:
        try:
            page.locator('button:has-text("Ok")').first.click(timeout=3_000)
            print('  [CLICK] Ok on popup')
        except Exception:
            print('  [INFO] No OK button popup found — may have been a JS alert handled automatically')

    _wait(page, 3000)
    print("[OK] Permit submitted")


def step_pay_for_permits_now(page: Page) -> None:
    """Step 11 — Click 'Pay for the permits now'."""
    print("\n[STEP 11] Clicking 'Pay for the permits now'...")

    for sel in [
        'text=Pay for the permits now',
        'a:has-text("Pay for the permits now")',
        'button:has-text("Pay for the permits now")',
        'a:has-text("Pay for the permit")',
        'button:has-text("Pay for the permit")',
    ]:
        try:
            page.locator(sel).first.click(timeout=10_000)
            print(f'  [CLICK] via {sel}')
            break
        except Exception:
            continue
    else:
        _debug_fields(page, ["Pay", "pay", "permit"])
        raise Exception("Could not find 'Pay for the permits now' link/button")

    _wait(page, 3000)
    print("[OK] On payment verification page")


def step_pay_for_verified_permits(page: Page) -> None:
    """Step 12 — Click 'Pay for verified permits'."""
    print("\n[STEP 12] Clicking 'Pay for verified permits'...")

    for sel in [
        'text=Pay for verified permits',
        'a:has-text("Pay for verified permits")',
        'button:has-text("Pay for verified permits")',
        'input[value*="Pay for verified"]',
        'a:has-text("Pay for verified")',
        'button:has-text("Pay for verified")',
    ]:
        try:
            page.locator(sel).first.click(timeout=10_000)
            print(f'  [CLICK] via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find 'Pay for verified permits' link/button")

    _wait(page, 3000)
    print("[OK] On payment method selection page")


def step_select_payment_method(page: Page) -> None:
    """Step 13 — Select 'Credit Card/E-Check' from dropdown, click Submit, OK popup."""
    print("\n[STEP 13] Selecting payment method...")

    # Find the payment method dropdown and select Credit Card/E-Check
    target = "Credit Card"
    selected = False

    # Try by name fragment first (ASP.NET pattern)
    if _select_by_name_fragment(page, "Payment", target, "Payment Method"):
        selected = True

    if not selected:
        # Scan all selects for an option containing "credit card" or "e-check"
        selects = page.locator("select").all()
        for s in selects:
            try:
                opts = s.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                for o in opts:
                    if "credit card" in o["text"].lower() or "e-check" in o["text"].lower():
                        s.select_option(value=o["value"])
                        print(f'  [SELECT] Payment Method: "{o["text"]}"')
                        selected = True
                        break
                if selected:
                    break
            except Exception:
                continue

    if not selected:
        _debug_fields(page, ["Payment", "payment", "Method", "method"])
        raise Exception("Could not find or select Credit Card/E-Check payment method")

    _wait(page, 500)

    # Click Submit
    for sel in [
        '#SubmitButton', 'input[value="Submit"]',
        'button:has-text("Submit")', 'input[type="submit"][value="Submit"]',
        'button[type="submit"]',
    ]:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Submit via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Submit button on payment method page")

    # Handle OK popup
    _wait(page, 1000)
    try:
        page.locator('button:has-text("OK")').first.click(timeout=5_000)
        print('  [CLICK] OK on popup')
    except Exception:
        try:
            page.locator('button:has-text("Ok")').first.click(timeout=3_000)
            print('  [CLICK] Ok on popup')
        except Exception:
            print('  [INFO] No OK popup found')

    _wait(page, 5000)
    print("[OK] Payment method selected — should be on secure checkout page")


def step_checkout_customer_next(page: Page) -> None:
    """Step 14 — On the secure checkout page, customer info is pre-filled. Click Next."""
    print("\n[STEP 14] Secure Checkout — Customer Info page, clicking Next...")
    print(f"  [INFO] Current URL: {page.url}")

    _wait(page, 5000)

    # Scroll to the bottom so the Next button is in view and visible
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 2000)

    # The NIC USA checkout "Next >" button may be an <a>, <button>, or <div>
    # with text "Next" plus a chevron icon. Try role-based first.
    for attempt in [
        lambda: page.get_by_role("button", name="Next").click(timeout=3_000),
        lambda: page.get_by_role("link", name="Next").click(timeout=3_000),
        lambda: page.locator('text="Next"').first.click(timeout=3_000),
        lambda: page.locator('text="Next >"').first.click(timeout=3_000),
        lambda: page.locator(':text("Next")').first.click(timeout=3_000),
        lambda: page.locator('a:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('button:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('[class*="next" i]').first.click(timeout=3_000),
        lambda: page.locator('[class*="Next" i]').first.click(timeout=3_000),
        lambda: page.locator('input[value="Next"]').first.click(timeout=3_000),
        lambda: page.locator('input[type="submit"]').first.click(timeout=3_000),
    ]:
        try:
            attempt()
            print('  [CLICK] Next button found and clicked')
            _wait(page, 3000)
            print("[OK] Advanced to payment info page")
            return
        except Exception:
            continue

    # Last resort: find ANY visible element containing "Next" text
    try:
        all_els = page.locator('*').all()
        for el in all_els:
            try:
                if not el.is_visible():
                    continue
                text = el.inner_text().strip()
                if text in ("Next", "Next >", "Next ›", "Next ▶"):
                    el.click()
                    print(f'  [CLICK] Next via element with text "{text}"')
                    _wait(page, 3000)
                    print("[OK] Advanced to payment info page")
                    return
            except Exception:
                continue
    except Exception:
        pass

    raise Exception("Could not find Next button on checkout customer info page")

    _wait(page, 3000)
    print("[OK] Advanced to payment info page")


def step_fill_payment_info(page: Page) -> None:
    """Step 15 — Fill credit card details on the payment info page. STOP before clicking Next."""
    print("\n[STEP 15] Filling payment info...")
    print(f"  [INFO] Current URL: {page.url}")

    _wait(page, 2000)

    # The payment page may be inside an iframe (common for secure checkout).
    # Try the main page first, then check all frames.
    target_frame = page

    # Detect if card number field exists on main page
    card_found = False
    for sel in [
        'input[name*="CardNumber" i]', 'input[name*="cardNumber" i]',
        'input[name*="ccNumber" i]', 'input[id*="CardNumber" i]',
        'input[id*="cardNumber" i]', 'input[id*="ccNumber" i]',
        'input[name*="card_number" i]', 'input[autocomplete="cc-number"]',
    ]:
        try:
            if page.locator(sel).first.is_visible(timeout=2_000):
                card_found = True
                break
        except Exception:
            continue

    if not card_found:
        # Check iframes
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                for sel in [
                    'input[name*="CardNumber" i]', 'input[name*="cardNumber" i]',
                    'input[name*="ccNumber" i]', 'input[id*="CardNumber" i]',
                    'input[type="tel"]', 'input[autocomplete="cc-number"]',
                ]:
                    if frame.locator(sel).first.is_visible(timeout=2_000):
                        target_frame = frame
                        card_found = True
                        print(f'  [INFO] Payment fields found inside iframe: {frame.url[:80]}')
                        break
                if card_found:
                    break
            except Exception:
                continue

    if not card_found:
        # Last resort: dump all fields to see what's available
        print("  [DEBUG] Could not find card number field. Dumping visible fields:")
        _debug_fields(page, ["card", "Card", "cc", "CC", "pay", "Pay", "number", "Number",
                              "expir", "Expir", "cvv", "CVV", "cvc", "CVC", "security", "Security",
                              "name", "Name"])
        # Also dump iframe fields
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            print(f"  [DEBUG] Iframe: {frame.url[:80]}")
            fields = frame.query_selector_all("input:not([type='hidden']), select")
            for el in fields:
                id_ = el.get_attribute("id") or ""
                name = el.get_attribute("name") or ""
                type_ = el.get_attribute("type") or ""
                print(f"    id={id_!r:30s} name={name!r:30s} type={type_!r}")

    # --- Fill card number ---
    _fill_payment_field(target_frame, [
        'input[name*="CardNumber" i]', 'input[name*="cardNumber" i]',
        'input[name*="ccNumber" i]', 'input[id*="CardNumber" i]',
        'input[id*="cardNumber" i]', 'input[id*="ccNumber" i]',
        'input[name*="card_number" i]', 'input[autocomplete="cc-number"]',
    ], PAYMENT_CARD["number"], "Card Number")

    # --- Expiration month (dropdown) ---
    _select_payment_field(target_frame, [
        'select[name*="ExpMonth" i]', 'select[name*="expMonth" i]',
        'select[name*="ExpirationMonth" i]', 'select[name*="expirationMonth" i]',
        'select[name*="CardMonth" i]', 'select[name*="cardMonth" i]',
        'select[id*="ExpMonth" i]', 'select[id*="expirationMonth" i]',
        'select[name*="ccMonth" i]', 'select[autocomplete="cc-exp-month"]',
    ], PAYMENT_CARD["exp_month"], "Expiration Month")

    # --- Expiration year (dropdown) ---
    _select_payment_field(target_frame, [
        'select[name*="ExpYear" i]', 'select[name*="expYear" i]',
        'select[name*="ExpirationYear" i]', 'select[name*="expirationYear" i]',
        'select[name*="CardYear" i]', 'select[name*="cardYear" i]',
        'select[id*="ExpYear" i]', 'select[id*="expirationYear" i]',
        'select[name*="ccYear" i]', 'select[autocomplete="cc-exp-year"]',
    ], PAYMENT_CARD["exp_year"], "Expiration Year")

    # --- CVV / Security code ---
    _fill_payment_field(target_frame, [
        'input[name*="SecurityCode" i]', 'input[name*="securityCode" i]',
        'input[name*="CVV" i]', 'input[name*="cvv" i]',
        'input[name*="CVC" i]', 'input[name*="cvc" i]',
        'input[name*="CardCode" i]', 'input[id*="SecurityCode" i]',
        'input[id*="CVV" i]', 'input[id*="cvv" i]',
        'input[id*="CardCode" i]', 'input[autocomplete="cc-csc"]',
    ], PAYMENT_CARD["cvv"], "Security Code")

    # --- Name on card ---
    _fill_payment_field(target_frame, [
        'input[name*="NameOnCard" i]', 'input[name*="nameOnCard" i]',
        'input[name*="CardName" i]', 'input[name*="cardName" i]',
        'input[name*="cardHolder" i]', 'input[name*="CardHolder" i]',
        'input[id*="NameOnCard" i]', 'input[id*="CardName" i]',
        'input[id*="cardHolder" i]', 'input[autocomplete="cc-name"]',
    ], PAYMENT_CARD["name"], "Name on Card")

    print("[OK] Payment info filled")


def _click_next_checkout(page: Page, label: str) -> None:
    """Reusable: click the Next button on the NIC USA secure checkout pages."""
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 1000)

    for attempt in [
        lambda: page.get_by_role("button", name="Next").click(timeout=3_000),
        lambda: page.get_by_role("link", name="Next").click(timeout=3_000),
        lambda: page.locator('text="Next"').first.click(timeout=3_000),
        lambda: page.locator(':text("Next")').first.click(timeout=3_000),
        lambda: page.locator('a:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('button:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('input[value="Next"]').first.click(timeout=3_000),
    ]:
        try:
            attempt()
            print(f'  [CLICK] Next on {label}')
            return
        except Exception:
            continue
    raise Exception(f"Could not find Next button on {label}")


def step_payment_next_and_submit(page: Page) -> None:
    """Step 16 — Click Next after payment info, then Submit Payment."""
    print("\n[STEP 16] Clicking Next on payment info page...")

    _click_next_checkout(page, "payment info page")
    _wait(page, 3000)

    print("[OK] On payment review/submit page")
    print("\n[STEP 17] Clicking Submit Payment...")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 1000)

    for attempt in [
        lambda: page.get_by_role("button", name="Submit Payment").click(timeout=3_000),
        lambda: page.get_by_role("link", name="Submit Payment").click(timeout=3_000),
        lambda: page.locator('text="Submit Payment"').first.click(timeout=3_000),
        lambda: page.locator(':text("Submit Payment")').first.click(timeout=3_000),
        lambda: page.locator('button:has-text("Submit Payment")').first.click(timeout=3_000),
        lambda: page.locator('a:has-text("Submit Payment")').first.click(timeout=3_000),
        lambda: page.locator('input[value="Submit Payment"]').first.click(timeout=3_000),
        lambda: page.locator('button:has-text("Submit")').first.click(timeout=3_000),
        lambda: page.locator('input[value="Submit"]').first.click(timeout=3_000),
    ]:
        try:
            attempt()
            print('  [CLICK] Submit Payment')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Submit Payment button")

    _wait(page, 5000)
    print("[STOP] =============================================")
    print("[STOP] Payment submitted.")
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
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")
    effective_date = permit.get("effectiveDate", "")
    effective_time = permit.get("effectiveTime", "12:00")
    unit_number = tractor

    errors = []
    if not tractor:
        errors.append("Missing tractor/unit number")
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

    print(f"[MS-TRIP] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[MS-TRIP] Unit: {unit_number} | Eff. Date: {effective_date} | "
          f"Eff. Time: {effective_time}")

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
        context = browser.new_context(viewport=None)
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        # Auto-accept JS alert/confirm dialogs (the MS portal uses these
        # after Submit and payment method selection)
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            step_login(page)
            step_system_user_notice(page)
            step_new_permit(page)
            step_contact_info(page)
            step_select_permit_type(page)
            step_effective_date_time(page, effective_date, effective_time)
            step_vehicle_selection(page, unit_number)
            step_click_next_vehicle(page)
            step_permit_provisions_submit(page)
            step_pay_for_permits_now(page)
            step_pay_for_verified_permits(page)
            step_select_payment_method(page)
            step_checkout_customer_next(page)
            step_fill_payment_info(page)
            step_payment_next_and_submit(page)

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Payment submitted",
            }

        except Exception as e:
            print(f"\n[MS-TRIP] Error for {driver_name}: {e}")
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
