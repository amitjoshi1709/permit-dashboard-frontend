"""
Alabama DMV TAP — Trip & Fuel Permit Automation

Called by the Celery task with a permit dict from the backend.
The `on_captcha_needed` callback lets the Celery task signal the dashboard
and block until the user solves the CAPTCHA.

Data flow:
  Backend builds permit dict (driver details from Supabase + company constants)
  → run() converts it to the flat field dict the form steps expect
  → Step functions fill the Alabama portal form
  → Stops before payment
"""

import time
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://mydmv.revenue.alabama.gov/TAP/ITAP/_/#1"
SLOW_MO    = 300
TIMEOUT    = 30_000

# ---------------------------------------------------------------------------
# Transform: permit dict → flat form fields
# ---------------------------------------------------------------------------

def build_form_data(permit: dict, company: dict) -> dict:
    """
    Convert the backend permit dict + company constants into the flat
    key-value dict that the step functions expect (same shape as the old CSV).
    """
    driver = permit["driver"]
    permit_type = permit.get("permitType", "trip_fuel")

    # Map permitType to yes/no radio buttons
    trip_permit = "yes" if permit_type in ("trip_fuel", "trip") else "no"
    fuel_permit = "yes" if permit_type in ("trip_fuel", "fuel") else "no"

    return {
        # Company-level (same for every driver)
        "legal_name":     company["legal_name"],
        "dba":            company["dba"],
        "primary_email":  company["primary_email"],
        "confirm_email":  company["confirm_email"],
        "street":         company["street"],
        "unit_type":      company["unit_type"],
        "unit":           company["unit"],
        "city":           company["city"],
        "state":          company["state"],
        "zip":            company["zip"],
        "county":         company["county"],
        "country":        company["country"],

        # Driver/vehicle-level (from Supabase fleet table)
        "usdot":                      driver.get("usdot", ""),
        "fein":                       driver.get("fein", ""),
        "vin":                        driver.get("vin", ""),
        "unit_number":                driver.get("tractor", ""),
        "plate_number":               driver.get("tagNumber", ""),
        "vehicle_make":               driver.get("make", ""),
        "model_year":                 str(driver.get("year", "")),
        "vehicle_type":               "Tractor Truck",
        "gross_vehicle_weight":       "80000",
        "registration_jurisdiction":  driver.get("tagState", "FL"),

        # Permit-level
        "trip_permit":    trip_permit,
        "fuel_permit":    fuel_permit,
        "effective_date": permit.get("effectiveDate", ""),
    }


# ---------------------------------------------------------------------------
# Low-level helpers (unchanged from original)
# ---------------------------------------------------------------------------

def fill_by_label(page: Page, label_text: str, value: str) -> None:
    if not value:
        return
    try:
        page.get_by_label(label_text, exact=False).fill(value)
        print(f"  [fill]   '{label_text}' = {value!r}")
    except Exception as e:
        print(f"  [WARN]   Could not fill '{label_text}': {e}")


def select_by_label(page: Page, label_text: str, value: str) -> None:
    if not value:
        return
    try:
        loc = page.get_by_label(label_text, exact=False)
        try:
            loc.select_option(value=value)
        except Exception:
            loc.select_option(label=value)
        print(f"  [select] '{label_text}' = {value!r}")
    except Exception as e:
        print(f"  [WARN]   Could not select '{label_text}': {e}")


def _click_styled_radio(page: Page, group_index: int, answer: str) -> None:
    css_class = "FastComboButtonItem_Yes" if answer.strip().lower() == "yes" else "FastComboButtonItem_No"
    try:
        page.locator(f"label.{css_class}").nth(group_index).click()
        print(f"  [radio]  group {group_index} → {answer}")
    except Exception as e:
        print(f"  [WARN]   Styled radio click failed (group {group_index}, '{answer}'): {e}")


def _wait_for_page_settle(page: Page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(1.2)


def click_next(page: Page) -> None:
    selectors = [
        "button:has-text('Next')",
        "input[value='Next']",
        "button:has-text('Continue')",
        "a:has-text('Next')",
        "[id*='next' i]",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=5_000)
            page.click(sel)
            _wait_for_page_settle(page)
            print("  [next]   Clicked Next / Continue")
            return
        except PlaywrightTimeoutError:
            continue
    print("  [WARN]   Could not find Next button — waiting for manual click.")
    time.sleep(10)
    _wait_for_page_settle(page)


def click_verify_address(page: Page) -> None:
    verify_selectors = [
        "button:has-text('Verify Address')",
        "input[value='Verify Address']",
        "button:has-text('Verify')",
        "a:has-text('Verify Address')",
    ]
    for sel in verify_selectors:
        try:
            page.wait_for_selector(sel, timeout=8_000)
            page.click(sel)
            _wait_for_page_settle(page)
            time.sleep(1.0)
            print(f"  [verify] Clicked Verify Address")
            _accept_address_dialog(page)
            return
        except PlaywrightTimeoutError:
            continue
    print("  [WARN]   Could not find 'Verify Address' button.")


def _accept_address_dialog(page: Page) -> None:
    time.sleep(0.8)
    accept_selectors = [
        "button:has-text('Save')",
        "button:has-text('Use as Entered')",
        "button:has-text('Use Entered Address')",
        "button:has-text('Accept')",
        "button:has-text('Confirm')",
        "button:has-text('OK')",
    ]
    for sel in accept_selectors:
        try:
            page.wait_for_selector(sel, timeout=4_000)
            page.click(sel)
            _wait_for_page_settle(page)
            print(f"  [addr]   Accepted address dialog: {sel!r}")
            return
        except PlaywrightTimeoutError:
            continue


def debug_fields(page: Page) -> None:
    print("\n" + "=" * 70)
    print("DEBUG — form fields on this page:")
    print("=" * 70)
    fields = page.query_selector_all("input:not([type='hidden']), select, textarea")
    for el in fields:
        id_    = el.get_attribute("id") or ""
        name   = el.get_attribute("name") or ""
        type_  = el.get_attribute("type") or ""

        label_text = ""
        if id_:
            lbl = page.query_selector(f"label[for='{id_}']")
            if lbl:
                label_text = lbl.inner_text().strip()
        if not label_text:
            label_text = el.get_attribute("aria-label") or ""
        if not label_text:
            label_text = el.evaluate(
                "el => { const l = el.closest('label'); return l ? l.innerText.trim() : ''; }"
            )

        print(
            f"  LABEL={label_text!r:38s} "
            f"id={id_!r:14s} "
            f"type={type_!r:12s} "
            f"name={name!r}"
        )
    print("=" * 70 + "\n")


def is_payment_page(page: Page) -> bool:
    url     = page.url.lower()
    title   = page.title().lower()
    h       = page.query_selector("h1, h2, h3")
    heading = h.inner_text().lower() if h else ""
    return (
        "payment" in url or "pay" in url
        or "payment" in title
        or "payment" in heading or "pay now" in heading
        or "payment options" in heading
    )


def search_lookup_field(page: Page, field_label: str, search_term: str) -> None:
    try:
        field = page.get_by_label(field_label, exact=False)
        btn = field.locator("xpath=ancestor::tr//button[contains(@class,'DocControlFileButton')]")
        if btn.count() == 0:
            btn = page.locator("button.DocControlFileButton").first

        btn.click()
        print(f"  [lookup] Clicked search button for '{field_label}'")

        try:
            page.wait_for_selector("button:has-text('Search'):visible", timeout=8_000)
        except PlaywrightTimeoutError:
            iframes = page.locator("iframe:visible").all()
            for iframe in iframes:
                frame = iframe.content_frame()
                if frame:
                    try:
                        frame.wait_for_selector("button:has-text('Search')", timeout=3_000)
                        frame.get_by_role("textbox").first.fill(search_term)
                        frame.locator("button:has-text('Search')").first.click()
                        time.sleep(2.0)
                        frame.locator(f"text={search_term}").first.click()
                        _wait_for_page_settle(page)
                        print(f"  [lookup] '{field_label}' = {search_term!r} (iframe)")
                        return
                    except Exception:
                        continue
            raise Exception("Search overlay / iframe did not appear after button click")

        all_visible = page.locator("input[type='text']:visible").all()
        if not all_visible:
            raise Exception("No visible text inputs found in search overlay")

        search_input = all_visible[-1]
        search_input.fill(search_term)
        print(f"  [lookup] Entered search term {search_term!r}")

        page.locator("button:has-text('Search'):visible").last.click()
        time.sleep(2.0)

        page.locator(f"text={search_term}").first.click()
        _wait_for_page_settle(page)
        print(f"  [lookup] '{field_label}' = {search_term!r}")

    except Exception as e:
        print(f"  [WARN]   Lookup search failed for '{field_label}': {e}")


# ---------------------------------------------------------------------------
# Page steps (unchanged from original)
# ---------------------------------------------------------------------------

def step_navigate(page: Page) -> None:
    print("\n[STEP 1] Navigating to Alabama DMV TAP portal...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    print(f"  Loaded: {page.url}")


def step_click_permit_link(page: Page) -> None:
    print("\n[STEP 2] Clicking 'Request Trip or Fuel Permit'...")
    selectors = [
        "text=Request Trip or Fuel Permit",
        "a:has-text('Trip')",
        "a:has-text('Fuel Permit')",
        "button:has-text('Trip')",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=5_000)
            page.click(sel)
            _wait_for_page_settle(page)
            print(f"  Clicked: {sel!r}")
            return
        except PlaywrightTimeoutError:
            continue

    print("  [WARN] Could not find the permit link.")
    for link in page.query_selector_all("a"):
        text = link.inner_text().strip()
        if text:
            print(f"    {text!r}")


def step_captcha(page: Page, on_captcha_needed: Optional[Callable] = None) -> None:
    print("\n[STEP 3] About / intro page — CAPTCHA required.")
    debug_fields(page)

    if on_captcha_needed:
        on_captcha_needed()
    else:
        print("\n" + "=" * 60)
        print("  ACTION REQUIRED — solve the CAPTCHA in the browser,")
        print("  then press ENTER here to continue.")
        print("=" * 60)
        input("  Press ENTER after solving CAPTCHA: ")

    click_next(page)


def step_page1_identification(page: Page, data: dict) -> None:
    print("\n[STEP 4] Page 1 — Identification...")
    debug_fields(page)

    fill_by_label(page, "USDOT", data["usdot"])

    try:
        page.get_by_role("textbox", name="FEIN").fill(data["fein"])
        print(f"  [fill]   'FEIN' = {data['fein']!r}")
    except Exception as e:
        print(f"  [WARN]   FEIN fill failed: {e}")

    fill_by_label(page, "Legal Name",     data["legal_name"])
    fill_by_label(page, "Doing Business", data["dba"])

    try:
        primary = page.get_by_role("textbox", name="Primary E-mail Address")
        primary.fill(data["primary_email"])
        print(f"  [fill]   'Primary E-mail Address' = {data['primary_email']!r}")
        primary.press("Tab")
        time.sleep(0.6)
    except Exception as e:
        print(f"  [WARN]   Primary email fill failed: {e}")

    try:
        confirm = page.get_by_role("textbox", name="Confirm Email")
        page.wait_for_function(
            """() => {
                const els = document.querySelectorAll("input[type='email']");
                for (const el of els) {
                    if (el.getAttribute('name') !== document.querySelector("input[type='email'][placeholder]")?.getAttribute('name')
                        && !el.disabled) return true;
                }
                return false;
            }""",
            timeout=5_000,
        )
        confirm.fill(data["confirm_email"])
        print(f"  [fill]   'Confirm Email' = {data['confirm_email']!r}")
    except Exception as e:
        print(f"  [WARN]   Confirm email fill failed: {e}")

    _click_styled_radio(page, group_index=0, answer=data["trip_permit"])
    _click_styled_radio(page, group_index=1, answer=data["fuel_permit"])

    fill_by_label(page, "Effective Date", data["effective_date"])

    click_next(page)


def step_page2_mailing_address(page: Page, data: dict) -> None:
    print("\n[STEP 5] Page 2 — Mailing Address...")
    debug_fields(page)

    try:
        page.get_by_role("textbox", name="Street *").fill(data["street"])
        print(f"  [fill]   'Street' = {data['street']!r}")
    except Exception:
        try:
            page.locator("input[type='text'][aria-required='true']").first.fill(data["street"])
            print(f"  [fill]   'Street' (fallback) = {data['street']!r}")
        except Exception as e:
            print(f"  [WARN]   Street fill failed: {e}")

    select_by_label(page, "Unit Type", data["unit_type"])

    try:
        page.get_by_role("textbox", name="Unit").fill(data["unit"])
        print(f"  [fill]   'Unit' = {data['unit']!r}")
    except Exception as e:
        print(f"  [WARN]   Unit fill failed: {e}")

    fill_by_label(page, "City",      data["city"])
    select_by_label(page, "State",   data["state"])
    fill_by_label(page, "Zip",       data["zip"])
    select_by_label(page, "Country", data["country"])

    click_verify_address(page)

    try:
        county_sel  = page.get_by_label("County", exact=True)
        current_val = county_sel.evaluate("el => el.value")
        options     = county_sel.evaluate(
            "el => Array.from(el.options).slice(0,5).map(o => ({value: o.value, text: o.text.trim()}))"
        )
        print(f"  [county] Current value after verify: {current_val!r}")
        if not current_val:
            for attempt in [data["county"], data["county"].replace("-", " "), data["county"].title()]:
                try:
                    county_sel.select_option(label=attempt)
                    print(f"  [select] 'County' = {attempt!r}")
                    break
                except Exception:
                    try:
                        county_sel.select_option(value=attempt)
                        print(f"  [select] 'County' (value) = {attempt!r}")
                        break
                    except Exception:
                        continue
    except Exception as e:
        print(f"  [WARN]   County: {e}")

    click_next(page)


def step_page3_vehicle_details(page: Page, data: dict) -> None:
    print("\n[STEP 6] Page 3 — Vehicle Details...")
    debug_fields(page)

    fill_by_label(page, "VIN",          data["vin"])
    fill_by_label(page, "Unit Number",  data["unit_number"])
    fill_by_label(page, "Plate Number", data["plate_number"])
    select_by_label(page, "Vehicle Type", data["vehicle_type"])

    search_lookup_field(page, "Vehicle Make", data["vehicle_make"])

    fill_by_label(page, "Model Year",          data["model_year"])
    fill_by_label(page, "Gross Vehicle Weight", data["gross_vehicle_weight"])

    try:
        reg_sel = page.get_by_label("Registration Jurisdiction", exact=False)
        reg_sel.select_option(value=data["registration_jurisdiction"])
        print(f"  [select] 'Registration Jurisdiction' = {data['registration_jurisdiction']!r}")
    except Exception as e:
        print(f"  [WARN]   Registration Jurisdiction: {e}")

    click_next(page)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(permit: dict, job_id: str, on_captcha_needed: Optional[Callable] = None, company: dict = None) -> dict:
    """
    Run the Alabama trip/fuel permit automation for one driver.

    Args:
        permit: Enriched permit dict from the backend containing driver details
                and company constants.
        job_id: The parent job ID (for logging).
        on_captcha_needed: Callback invoked when CAPTCHA page is reached.
                          Should block until user solves it. If None, waits
                          for terminal input (standalone/testing use).
        company: Company constants dict (legal_name, address, email, etc.).
                 Passed in by the Celery task from config.py.

    Returns:
        Result dict with "status" and "permitId" keys.
    """
    COMPANY = company

    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver["tractor"]
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")

    # Build the flat form data dict from permit + company constants
    data = build_form_data(permit, COMPANY)
    print(f"[Alabama] Starting permit {permit_id} for {driver_name} ({tractor})")

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
            step_navigate(page)
            step_click_permit_link(page)
            step_captcha(page, on_captcha_needed=on_captcha_needed)

            if is_payment_page(page):
                print(f"[Alabama] Reached payment page early — stopping.")
                return {
                    "permitId": permit_id,
                    "driverName": driver_name,
                    "tractor": tractor,
                    "permitType": permit_type,
                    "status": "success",
                    "message": "Reached payment page",
                }

            step_page1_identification(page, data)

            if is_payment_page(page):
                return {
                    "permitId": permit_id,
                    "driverName": driver_name,
                    "tractor": tractor,
                    "permitType": permit_type,
                    "status": "success",
                    "message": "Reached payment page",
                }

            step_page2_mailing_address(page, data)

            if is_payment_page(page):
                return {
                    "permitId": permit_id,
                    "driverName": driver_name,
                    "tractor": tractor,
                    "permitType": permit_type,
                    "status": "success",
                    "message": "Reached payment page",
                }

            step_page3_vehicle_details(page, data)

            print(f"\n[Alabama] Reached payment page — stopping as requested.")
            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Reached payment page",
            }

        except Exception as e:
            print(f"\n[Alabama] Error for {driver_name}: {e}")
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
