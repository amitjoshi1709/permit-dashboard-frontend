"""
South Carolina SCDMV — Trip & Fuel Permit Automation

Portal: https://www.scdmvonline.com/SCTRNS/Member/MCS/logon.aspx
Permit types: FIP (Combination IFTA/IRP), FTP (IFTA Fuel), ITP (IRP Trip)
Login: Required (SC_PORTAL_USERNAME / SC_PORTAL_PASSWORD)
Automation boundary: Fills all form fields through payment. Stops or pays
  depending on whether a payment card is configured.

The portal is ASP.NET WebForms — field names use ctl00$ContentPlaceHolder1$...
prefixes. We use a mix of name-fragment and label-based selectors.

Data flow:
  Backend builds permit dict (driver details from Supabase + company constants)
  → run() logs in, navigates to Trip Permits, fills the form, proceeds to payment.
"""

import os
import re
import time
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://www.scdmvonline.com/SCTRNS/Member/MCS/logon.aspx"
SLOW_MO = 300
TIMEOUT = 30_000

# Map permitType values to the SC portal dropdown labels
PERMIT_TYPE_MAP = {
    "trip_fuel": "FIP - Combination IFTA/IRP Trip Permits",
    "trip":      "ITP - IRP Trip Permit",
    "fuel":      "FTP - IFTA Fuel Permit",
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


def _format_datetime(date_str: str, time_str: str = "") -> str:
    """Format to SC portal datetime: MM/DD/YYYY HH:MM:SS AM/PM."""
    date = _iso_to_mmddyyyy(date_str)
    if not date:
        return ""
    if not time_str:
        time_str = "12:00"
    parts = time_str.replace(":", " ").split()
    h = int(parts[0]) if parts else 12
    m = int(parts[1]) if len(parts) > 1 else 0
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{date} {str(h12).zfill(2)}:{str(m).zfill(2)}:00 {period}"


def _debug_fields(page: Page) -> None:
    fields = page.query_selector_all("input:not([type='hidden']), select, textarea")
    printed = 0
    for el in fields:
        id_ = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        if "ZZ" in id_ or (not id_ and not name):
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
        print("  (no fields found)")


def _fill(page: Page, selector: str, value: str, label: str) -> bool:
    if not value:
        return False
    try:
        loc = page.locator(selector).first
        if loc.is_visible(timeout=3_000):
            loc.click(click_count=3)
            loc.fill(value)
            print(f'  [FILL] {label}: "{value}"')
            return True
    except Exception:
        pass
    print(f'  [MISS] Could not fill {label}')
    return False


def _select(page: Page, selector: str, value: str, label: str) -> bool:
    if not value:
        return False
    try:
        loc = page.locator(selector).first
        if loc.is_visible(timeout=3_000):
            opts = loc.evaluate(
                "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
            )
            val_lower = value.lower()
            for o in opts:
                if o["text"] == value or o["value"] == value:
                    loc.select_option(value=o["value"])
                    print(f'  [SELECT] {label}: "{o["text"]}"')
                    return True
            for o in opts:
                if val_lower in o["text"].lower() or val_lower in o["value"].lower():
                    loc.select_option(value=o["value"])
                    print(f'  [SELECT] {label}: "{o["text"]}" (fuzzy)')
                    return True
            print(f'  [WARN] No match for {label}={value!r}. Options:')
            for o in opts[:15]:
                print(f'    - {o["text"]!r}')
    except Exception:
        pass
    print(f'  [MISS] Could not select {label}')
    return False


def _fill_by_label(page: Page, label_text: str, value: str) -> bool:
    if not value:
        return False
    try:
        loc = page.get_by_label(label_text, exact=False)
        if loc.count() > 0 and loc.first.is_visible():
            loc.first.fill("")
            loc.first.fill(value)
            print(f'  [FILL] {label_text}: "{value}"')
            return True
    except Exception:
        pass
    print(f'  [MISS] Could not fill {label_text}')
    return False


def _select_by_label(page: Page, label_text: str, value: str) -> bool:
    if not value:
        return False
    try:
        loc = page.get_by_label(label_text, exact=False)
        if loc.count() > 0 and loc.first.is_visible():
            opts = loc.first.evaluate(
                "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
            )
            val_lower = value.lower()
            for o in opts:
                if o["text"] == value or o["value"] == value:
                    loc.first.select_option(value=o["value"])
                    print(f'  [SELECT] {label_text}: "{o["text"]}"')
                    return True
            for o in opts:
                if val_lower in o["text"].lower() or val_lower in o["value"].lower():
                    loc.first.select_option(value=o["value"])
                    print(f'  [SELECT] {label_text}: "{o["text"]}" (fuzzy)')
                    return True
            print(f'  [WARN] No match for {label_text}={value!r}')
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def step_login(page: Page) -> None:
    print("\n[STEP 1] Logging in to SC SCDMV portal...")

    username = os.getenv("SC_PORTAL_USERNAME", "")
    password = os.getenv("SC_PORTAL_PASSWORD", "")
    if not username or not password:
        raise Exception("SC_PORTAL_USERNAME or SC_PORTAL_PASSWORD not set in .env")

    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    _wait(page, 3000)

    # Fill User ID and Password
    for sel in ['input[name*="UserID" i]', 'input[name*="userId" i]', 'input[id*="UserID" i]',
                'input[type="text"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.fill(username)
                print(f'  [FILL] User ID via {sel}')
                break
        except Exception:
            continue

    try:
        page.locator('input[type="password"]').first.fill(password)
        print('  [FILL] Password')
    except Exception:
        raise Exception("Could not find Password field")

    # Click LOGIN
    for sel in ['input[value="LOGIN"]', 'input[value="Login"]', 'button:has-text("Login")',
                'input[type="submit"]', 'button[type="submit"]']:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] Login via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find LOGIN button")

    _wait(page, 3000)
    print("[OK] Logged in")


def step_post_login_submit(page: Page) -> None:
    """Step 2 — Click Submit on the post-login intro page."""
    print("\n[STEP 2] Post-login submit...")

    for sel in ['input[value="Submit"]', 'button:has-text("Submit")', 'input[type="submit"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Submit via {sel}')
                break
        except Exception:
            continue

    _wait(page, 3000)
    print("[OK] Post-login submitted")


def step_navigate_to_mcs(page: Page) -> None:
    """Step 3 — Click MCS Web Portal link."""
    print("\n[STEP 3] Navigating to MCS Web Portal...")

    for sel in ['a:has-text("MCS Web Portal")', 'text=MCS Web Portal',
                'a:has-text("Motor Carrier")', 'text=Motor Carrier Services']:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] MCS via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find MCS Web Portal link")

    _wait(page, 3000)
    print("[OK] On MCS portal")


def step_navigate_to_trip_permits(page: Page) -> None:
    """Step 4 — Click Services → Trip Permits in sidebar."""
    print("\n[STEP 4] Navigating to Trip Permits...")

    # Expand Services if needed
    for sel in ['a:has-text("Services")', 'text=Services']:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print('  [CLICK] Services')
            break
        except Exception:
            continue

    _wait(page, 1000)

    # Click Trip Permits
    for sel in ['a:has-text("Trip Permits")', 'text=Trip Permits']:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print('  [CLICK] Trip Permits')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Trip Permits link")

    _wait(page, 2000)
    print("[OK] On Trip Permits page")


def step_click_trip_permit(page: Page) -> None:
    """Step 5 — Click Trip Permit link inside the panel (not the sidebar link)."""
    print("\n[STEP 5] Clicking Trip Permit link in panel...")

    _wait(page, 2000)

    # The page has a Trip Permit panel with links. The sidebar also has "Trip Permits".
    # We need the one in the main content area, not the sidebar.
    # Strategy: find all "Trip Permit" links, skip any that are in the sidebar/nav,
    # and click the one in the main content that says exactly "Trip Permit" (not "Trip Permits").
    clicked = False
    links = page.locator('a').all()
    for link in links:
        try:
            if not link.is_visible():
                continue
            text = link.inner_text().strip()
            # Skip sidebar links (they say "Trip Permits" plural or are in nav)
            if text == "Trip Permits":
                continue
            if "hunter" in text.lower():
                continue
            # Match "Trip Permit" (singular) in the panel
            if text == "Trip Permit" or text.lower() == "trip permit":
                link.click()
                print(f'  [CLICK] Panel link: "{text}"')
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        # Fallback: dump visible links for debugging
        print("  [DEBUG] Visible links on page:")
        for link in links:
            try:
                if link.is_visible():
                    text = link.inner_text().strip()
                    if text and len(text) < 50:
                        print(f"    - {text!r}")
            except Exception:
                pass
        raise Exception("Could not find 'Trip Permit' link in panel")

    _wait(page, 2000)
    print("[OK] On New Permit page")


def step_search_proceed(page: Page) -> None:
    """Step 6 — Customer # is prefilled. Click Proceed."""
    print("\n[STEP 6] Clicking Proceed on search page...")

    for sel in ['input[value="Proceed"]', 'button:has-text("Proceed")',
                'input[type="submit"]']:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Proceed via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Proceed button")

    _wait(page, 3000)
    print("[OK] On Permit Details page")


def step_fill_permit_details(page: Page, permit_type_label: str, effective_datetime: str) -> None:
    """Step 7a — Fill Permit Type and Effective Date."""
    print("\n[STEP 7a] Filling Permit Details...")

    _debug_fields(page)

    # Permit Type dropdown
    selected = False
    for sel in ['select[name*="PermitType" i]', 'select[id*="PermitType" i]']:
        if _select(page, sel, permit_type_label, "Permit Type"):
            selected = True
            break
    if not selected:
        _select_by_label(page, "Permit Type", permit_type_label)

    _wait(page, 1000)

    # Effective Date
    for sel in ['input[name*="EffectiveDate" i]', 'input[id*="EffectiveDate" i]',
                'input[name*="PermitEffDate" i]', 'input[id*="PermitEffDate" i]']:
        if _fill(page, sel, effective_datetime, "Effective Date"):
            break
    else:
        _fill_by_label(page, "Permit Effective Date", effective_datetime)

    print("[OK] Permit Details filled")


def step_fill_vehicle(page: Page, driver: dict) -> None:
    """Step 7b — Fill vehicle details. Enter VIN first and click Find."""
    print("\n[STEP 7b] Filling Vehicle Details...")

    vin = driver.get("vin", "")
    tractor = driver.get("tractor", "")
    first_name = driver.get("firstName", "")
    last_name = driver.get("lastName", "")
    tag = driver.get("tagNumber", "")
    tag_state = driver.get("tagState", "FL")
    make = driver.get("make", "")
    year = str(driver.get("year", ""))

    # VIN first
    for sel in ['input[name*="VIN" i]', 'input[id*="VIN" i]']:
        if _fill(page, sel, vin, "VIN"):
            break
    else:
        _fill_by_label(page, "VIN", vin)

    # Click Find button if it exists
    _wait(page, 500)
    for sel in ['input[value="Find"]', 'button:has-text("Find")', 'input[value="Search"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                loc.click()
                print('  [CLICK] Find/Search button')
                _wait(page, 2000)
                break
        except Exception:
            continue

    # Registration/Unit #
    for sel in ['input[name*="UnitNo" i]', 'input[name*="Registration" i]',
                'input[id*="UnitNo" i]', 'input[id*="Registration" i]']:
        if _fill(page, sel, tractor, "Registration/Unit #"):
            break
    else:
        _fill_by_label(page, "Registration", tractor)

    # Owner
    owner = f"{first_name} {last_name}".strip()
    for sel in ['input[name*="Owner" i]', 'input[id*="Owner" i]']:
        if _fill(page, sel, owner, "Owner"):
            break
    else:
        _fill_by_label(page, "Owner", owner)

    # Plate
    for sel in ['input[name*="Plate" i]', 'input[id*="Plate" i]',
                'input[name*="TagNo" i]', 'input[id*="TagNo" i]']:
        if _fill(page, sel, tag, "Plate"):
            break
    else:
        _fill_by_label(page, "Plate", tag)

    # Vehicle Type — "OH - Other"
    for sel in ['select[name*="VehicleType" i]', 'select[id*="VehicleType" i]',
                'select[name*="VehType" i]']:
        if _select(page, sel, "OH", "Vehicle Type"):
            break
    else:
        _select_by_label(page, "Vehicle Type", "OH")

    # Make
    for sel in ['input[name*="Make" i]', 'input[id*="Make" i]',
                'select[name*="Make" i]', 'select[id*="Make" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                tag_name = loc.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    _select(page, sel, make, "Make")
                else:
                    _fill(page, sel, make, "Make")
                break
        except Exception:
            continue

    # Year
    for sel in ['input[name*="Year" i]', 'input[id*="Year" i]']:
        if _fill(page, sel, year, "Year"):
            break
    else:
        _fill_by_label(page, "Year", year)

    # Gross Weight
    for sel in ['input[name*="GrossWeight" i]', 'input[name*="Weight" i]',
                'input[id*="GrossWeight" i]', 'input[id*="Weight" i]']:
        if _fill(page, sel, "80000", "Gross Weight"):
            break
    else:
        _fill_by_label(page, "Gross Weight", "80000")

    # Axles
    for sel in ['input[name*="Axle" i]', 'input[id*="Axle" i]',
                'select[name*="Axle" i]', 'select[id*="Axle" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                tag_name = loc.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    _select(page, sel, "5", "Axles")
                else:
                    _fill(page, sel, "5", "Axles")
                break
        except Exception:
            continue

    # State of Registration — there may be multiple State dropdowns on the page.
    # Look specifically for one related to registration, not mailing address.
    for sel in ['select[name*="RegState" i]', 'select[id*="RegState" i]',
                'select[name*="StateOfReg" i]', 'select[id*="StateOfReg" i]',
                'select[name*="StateReg" i]']:
        if _select(page, sel, tag_state, "State of Registration"):
            break
    else:
        # Fallback: try label-based
        if not _select_by_label(page, "State of Registration", tag_state):
            # Last resort: find all visible selects with state options and pick the right one
            selects = page.locator('select').all()
            for s in selects:
                try:
                    if not s.is_visible():
                        continue
                    opts = s.evaluate("el => Array.from(el.options).map(o => o.text.trim())")
                    # If it has state abbreviations like "FL", "GA", etc.
                    if any(o in opts for o in ["FL", "GA", "SC", "AL"]) or any("Florida" in o for o in opts):
                        # Check if this is the registration state (not mailing)
                        name = s.get_attribute("name") or ""
                        id_ = s.get_attribute("id") or ""
                        label_for = ""
                        if id_:
                            lbl = page.query_selector(f'label[for="{id_}"]')
                            if lbl:
                                label_for = lbl.inner_text().strip()
                        if "mail" in name.lower() or "mail" in id_.lower() or "mail" in label_for.lower():
                            continue
                        _select(page, f'#{id_}' if id_ else f'[name="{name}"]', tag_state, "State of Registration")
                        break
                except Exception:
                    continue

    print("[OK] Vehicle Details filled")


def step_fill_insurance(page: Page, driver: dict) -> None:
    """Step 7c — Fill insurance details."""
    print("\n[STEP 7c] Filling Insurance Details...")

    ins = driver.get("insurance", {})
    ins_company = ins.get("company", "") or driver.get("insuranceCompany", "")
    ins_eff = _iso_to_mmddyyyy(ins.get("effectiveDate", "") or driver.get("insuranceEffective", ""))
    ins_exp = _iso_to_mmddyyyy(ins.get("expirationDate", "") or driver.get("insuranceExpiration", ""))
    policy = ins.get("policyNumber", "") or driver.get("policyNumber", "")

    print(f"  [DEBUG] Insurance values: company={ins_company!r} eff={ins_eff!r} exp={ins_exp!r} policy={policy!r}")

    # Debug: show available fields so we can see exact names
    print("  [DEBUG] Insurance-related fields:")
    fields = page.query_selector_all("input:not([type='hidden']), select")
    for el in fields:
        id_ = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        if any(kw in (id_ + name).lower() for kw in ["policy", "insur", "ins", "company"]):
            type_ = el.get_attribute("type") or ""
            print(f"    id={id_!r:30s} name={name!r:40s} type={type_!r}")

    # Use exact IDs from the SC portal
    _fill(page, '#InsurancePolNo', policy, "Policy No.")
    _fill(page, '#InsuranceCompName', ins_company, "Insurance Company")
    _fill(page, '#InsurancePolEffDt', ins_eff, "Insurance Effective Date")
    _fill(page, '#InsurancePolExpDt', ins_exp, "Insurance Expiration Date")

    print("[OK] Insurance Details filled")


def step_fill_operator(page: Page, driver: dict) -> None:
    """Step 7d — Fill operator details (USDOT, FEIN)."""
    print("\n[STEP 7d] Filling Operator Details...")

    usdot = driver.get("usdot", "")
    fein = driver.get("fein", "")

    if usdot:
        _fill_by_label(page, "USDOT", usdot)
    if fein:
        _fill_by_label(page, "FEIN", fein)

    # Click CVIEW Check button
    _wait(page, 500)
    for sel in ['input[value="CVIEW Check"]', 'button:has-text("CVIEW Check")',
                'input[value*="CVIEW"]', 'button:has-text("CVIEW")',
                'a:has-text("CVIEW")']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3_000):
                loc.click()
                print(f'  [CLICK] CVIEW Check via {sel}')
                _wait(page, 3000)
                break
        except Exception:
            continue
    else:
        print("  [WARN] CVIEW Check button not found — continuing")

    print("[OK] Operator Details filled")


def step_proceed_to_payment(page: Page) -> None:
    """Step 8 — Click Proceed at the bottom of the form."""
    print("\n[STEP 8] Clicking Proceed to payment...")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 500)

    for sel in ['input[value="Proceed"]', 'button:has-text("Proceed")',
                'input[type="submit"][value="Proceed"]', 'input[type="submit"]']:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Proceed via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Proceed button")

    _wait(page, 3000)
    print("[OK] On payment/review page")


def step_pay_now(page: Page) -> None:
    """Step 9 — Click Pay Now, then on the next page click Electronic Payment."""
    print("\n[STEP 9] Clicking Pay Now...")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 1000)

    # Step 9a: Click Pay Now
    for sel in ['input[value="Pay Now"]', 'button:has-text("Pay Now")',
                'a:has-text("Pay Now")', 'input[value="Pay"]',
                'button:has-text("Pay")']:
        try:
            page.locator(sel).first.click(timeout=5_000)
            print(f'  [CLICK] Pay Now via {sel}')
            break
        except Exception:
            continue
    else:
        raise Exception("Could not find Pay Now button")

    _wait(page, 3000)

    # Step 9b: Click Electronic Payment on the next page
    print("  Clicking Electronic Payment...")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 1000)

    for sel in ['input[value="Electronic Payment"]', 'button:has-text("Electronic Payment")',
                'a:has-text("Electronic Payment")', 'input[value*="Electronic"]',
                'button:has-text("Electronic")', 'a:has-text("Electronic")',
                'text=Electronic Payment']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=5_000):
                loc.click()
                print(f'  [CLICK] Electronic Payment via {sel}')
                break
        except Exception:
            continue
    else:
        # Debug dump if not found
        print("  [DEBUG] Visible buttons on payment page:")
        for tag_sel in ['input[type="submit"]', 'input[type="button"]', 'button', 'a']:
            for el in page.locator(tag_sel).all():
                try:
                    if not el.is_visible():
                        continue
                    val = el.get_attribute("value") or ""
                    text = ""
                    try:
                        text = el.inner_text().strip()[:50]
                    except Exception:
                        pass
                    if val or text:
                        print(f"    val={val!r:25s} text={text!r}")
                except Exception:
                    pass
        raise Exception("Could not find Electronic Payment button")

    _wait(page, 5000)
    print("[OK] Payment initiated")


# ---------------------------------------------------------------------------
# NIC USA Secure Checkout (same pattern as AL/AR/MS)
# ---------------------------------------------------------------------------

CHECKOUT_CUSTOMER = {
    "country":    "United States",
    "first_name": "Erick",
    "last_name":  "Rodriguez",
    "address":    "5979 NW 151 ST Suite 101",
    "city":       "Miami Lakes",
    "state":      "FL - Florida",
    "zip":        "33014",
    "phone":      "786-332-5691",
    "email":      "info@megatruckingllc.com",
}


def _click_next_checkout(page: Page, label: str) -> None:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    for attempt in [
        lambda: page.get_by_role("button", name="Next").click(timeout=3_000),
        lambda: page.get_by_role("link", name="Next").click(timeout=3_000),
        lambda: page.locator('text="Next"').first.click(timeout=3_000),
        lambda: page.locator(':text("Next")').first.click(timeout=3_000),
        lambda: page.locator('a:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('button:has-text("Next")').first.click(timeout=3_000),
        lambda: page.locator('input[value="Next"]').first.click(timeout=3_000),
        lambda: page.locator('input[type="submit"]').first.click(timeout=3_000),
    ]:
        try:
            attempt()
            print(f'  [CLICK] Next on {label}')
            return
        except Exception:
            continue
    try:
        for el in page.locator('*').all():
            try:
                if el.is_visible() and el.inner_text().strip() in ("Next", "Next >", "Next ›"):
                    el.click()
                    print(f'  [CLICK] Next via text match on {label}')
                    return
            except Exception:
                continue
    except Exception:
        pass
    raise Exception(f"Could not find Next button on {label}")


def _fill_payment_field(frame, selectors, value, label):
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


def _select_payment_field(frame, selectors, value, label):
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


def step_checkout_select_payment_type(page: Page) -> None:
    """Select Credit Card from the payment type dropdown on the checkout page."""
    print("\n[STEP 10] Selecting payment type...")
    time.sleep(3)

    # Find ANY visible select on the checkout page and look for a credit card option
    selected = False
    selects = page.locator('select').all()
    for s in selects:
        try:
            if not s.is_visible():
                continue
            opts = s.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))")
            for o in opts:
                if "credit" in o["text"].lower() or "card" in o["text"].lower() or "e-check" in o["text"].lower():
                    s.select_option(value=o["value"])
                    print(f'  [SELECT] Payment Type: "{o["text"]}"')
                    selected = True
                    break
            if selected:
                break
        except Exception:
            continue

    if not selected:
        print("  [DEBUG] All visible selects on checkout page:")
        for s in selects:
            try:
                if not s.is_visible():
                    continue
                id_ = s.get_attribute("id") or ""
                name = s.get_attribute("name") or ""
                opts = s.evaluate("el => Array.from(el.options).map(o => o.text.trim()).slice(0, 10)")
                print(f"    id={id_!r:25s} name={name!r:25s} options={opts}")
            except Exception:
                pass
        print("  [WARN] Could not find payment type dropdown")

    _wait(page, 2000)

    # Click Next to advance past payment type selection
    try:
        _click_next_checkout(page, "payment type")
        _wait(page, 3000)
    except Exception:
        print("  [INFO] No Next button after payment type — may auto-advance")

    print("[OK] Payment type selected")


def step_checkout_fill_customer(page: Page) -> None:
    print("\n[STEP 11] Filling checkout customer info...")
    time.sleep(5)

    for label, value in [
        ("First Name",  CHECKOUT_CUSTOMER["first_name"]),
        ("Last Name",   CHECKOUT_CUSTOMER["last_name"]),
        ("Address",     CHECKOUT_CUSTOMER["address"]),
        ("City",        CHECKOUT_CUSTOMER["city"]),
        ("ZIP",         CHECKOUT_CUSTOMER["zip"]),
        ("Zip",         CHECKOUT_CUSTOMER["zip"]),
        ("Phone",       CHECKOUT_CUSTOMER["phone"]),
        ("Email",       CHECKOUT_CUSTOMER["email"]),
    ]:
        try:
            loc = page.get_by_label(label, exact=False)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.fill("")
                loc.first.fill(value)
                print(f'  [FILL] {label}: "{value}"')
        except Exception:
            pass

    for sel in ['select[name*="Country" i]', 'select[id*="Country" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                opts = loc.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))")
                for o in opts:
                    if "united states" in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] Country: "{o["text"]}"')
                        break
                break
        except Exception:
            continue

    for sel in ['select[name*="State" i]', 'select[id*="State" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                opts = loc.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))")
                for o in opts:
                    if "florida" in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] State: "{o["text"]}"')
                        break
                break
        except Exception:
            continue

    time.sleep(1)
    _click_next_checkout(page, "customer info")
    time.sleep(3)
    print("[OK] Customer info filled")


def step_checkout_fill_card(page: Page, payment_card: dict) -> None:
    print("\n[STEP 11] Filling card info...")
    time.sleep(2)

    target = page
    card_found = False
    for sel in [
        'input[name*="CardNumber" i]', 'input[id*="CardNumber" i]',
        'input[name*="ccNumber" i]', 'input[autocomplete="cc-number"]',
    ]:
        try:
            if page.locator(sel).first.is_visible(timeout=2_000):
                card_found = True
                break
        except Exception:
            continue

    if not card_found:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                for sel in ['input[name*="CardNumber" i]', 'input[id*="CardNumber" i]', 'input[type="tel"]']:
                    if frame.locator(sel).first.is_visible(timeout=2_000):
                        target = frame
                        card_found = True
                        break
                if card_found:
                    break
            except Exception:
                continue

    _fill_payment_field(target, [
        'input[name*="CardNumber" i]', 'input[id*="CardNumber" i]',
        'input[name*="ccNumber" i]', 'input[autocomplete="cc-number"]',
    ], payment_card["cardNumber"], "Card Number")

    _select_payment_field(target, [
        'select[name*="ExpMonth" i]', 'select[id*="ExpMonth" i]',
        'select[name*="ExpirationMonth" i]', 'select[autocomplete="cc-exp-month"]',
    ], payment_card["expMonth"], "Exp Month")

    _select_payment_field(target, [
        'select[name*="ExpYear" i]', 'select[id*="ExpYear" i]',
        'select[name*="ExpirationYear" i]', 'select[autocomplete="cc-exp-year"]',
    ], payment_card["expYear"], "Exp Year")

    _fill_payment_field(target, [
        'input[name*="SecurityCode" i]', 'input[name*="CVV" i]',
        'input[name*="CVC" i]', 'input[name*="CardCode" i]',
        'input[id*="SecurityCode" i]', 'input[id*="CVV" i]',
        'input[autocomplete="cc-csc"]',
    ], payment_card["cvv"], "CVV")

    _fill_payment_field(target, [
        'input[name*="NameOnCard" i]', 'input[name*="CardName" i]',
        'input[name*="cardHolder" i]', 'input[id*="NameOnCard" i]',
        'input[autocomplete="cc-name"]',
    ], payment_card["cardholderName"], "Name on Card")

    print("[OK] Card info filled")


def step_checkout_submit(page: Page) -> None:
    print("\n[STEP 12] Submitting payment...")

    _click_next_checkout(page, "payment info page")
    time.sleep(3)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)

    for attempt in [
        lambda: page.get_by_role("button", name="Submit Payment").click(timeout=3_000),
        lambda: page.get_by_role("link", name="Submit Payment").click(timeout=3_000),
        lambda: page.locator('text="Submit Payment"').first.click(timeout=3_000),
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
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")
    effective_date = permit.get("effectiveDate", "")
    effective_time = permit.get("effectiveTime", "12:00")

    # Map permit type to SC portal label
    permit_type_label = PERMIT_TYPE_MAP.get(permit_type)
    if not permit_type_label:
        return {
            "permitId": permit_id, "driverName": driver_name,
            "tractor": tractor, "permitType": permit_type,
            "status": "error",
            "message": f"Unsupported SC permit type: {permit_type}",
        }

    effective_datetime = _format_datetime(effective_date, effective_time)

    errors = []
    if not tractor:
        errors.append("Missing tractor/unit number")
    if not effective_date:
        errors.append("Missing effectiveDate")
    if not driver.get("vin"):
        errors.append("Missing VIN")

    if errors:
        return {
            "permitId": permit_id, "driverName": driver_name,
            "tractor": tractor, "permitType": permit_type,
            "status": "error",
            "message": f"Validation failed: {'; '.join(errors)}",
        }

    print(f"[SC-TRIP] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[SC-TRIP] Type: {permit_type_label} | Date: {effective_datetime}")

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
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            step_login(page)
            step_post_login_submit(page)
            step_navigate_to_mcs(page)
            step_navigate_to_trip_permits(page)
            step_click_trip_permit(page)
            step_search_proceed(page)
            step_fill_permit_details(page, permit_type_label, effective_datetime)
            step_fill_vehicle(page, driver)
            step_fill_insurance(page, driver)
            step_fill_operator(page, driver)
            step_proceed_to_payment(page)
            step_pay_now(page)

            # Electronic Payment opens a popup — wait for it to appear
            print("  [INFO] Waiting for checkout popup...")
            checkout_page = None
            for _ in range(10):
                all_pages = page.context.pages
                for p in all_pages:
                    if p != page:
                        checkout_page = p
                        break
                if checkout_page:
                    break
                time.sleep(1)

            if not checkout_page:
                # Try expect_page as fallback
                try:
                    with page.context.expect_page(timeout=10_000) as new_page_info:
                        pass
                    checkout_page = new_page_info.value
                except Exception:
                    checkout_page = page
                    print("  [WARN] No popup detected — using same page")

            if checkout_page != page:
                checkout_page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(3)
                print(f"  [INFO] Checkout popup: {checkout_page.url[:80]}")
            checkout_page.on("dialog", lambda dialog: dialog.accept())

            if payment_card and payment_card.get("cardNumber"):
                step_checkout_select_payment_type(checkout_page)
                step_checkout_fill_customer(checkout_page)
                step_checkout_fill_card(checkout_page, payment_card)
                step_checkout_submit(checkout_page)

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Payment submitted",
            }

        except Exception as e:
            print(f"\n[SC-TRIP] Error for {driver_name}: {e}")
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
