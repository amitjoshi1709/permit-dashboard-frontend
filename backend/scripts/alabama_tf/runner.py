"""
Alabama DMV TAP — Trip & Fuel Permit Automation

Called by the Celery task with a permit dict from the backend.
The `on_captcha_needed` callback lets the Celery task signal the dashboard
and block until the user solves the CAPTCHA.

Data flow:
  Backend builds permit dict (driver details from Supabase + company constants)
  → run() converts it to the flat field dict the form steps expect
  → Step functions fill the Alabama portal form
  → Proceeds through payment on NIC USA secure checkout
"""

import os
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


def _wait_for_busy_overlay(page: Page, timeout: int = 15_000) -> None:
    """Wait for the FastBusyOverlay to disappear before interacting with the page."""
    try:
        page.wait_for_selector("#FastBusyOverlay", state="hidden", timeout=timeout)
    except PlaywrightTimeoutError:
        # Overlay still visible; give it one more brief wait
        time.sleep(1.0)


def search_lookup_field(page: Page, field_label: str, search_term: str) -> None:
    """
    Perform a lookup search in Alabama TAP's modal field picker.
    Raises an exception on failure so the caller can stop the automation
    (instead of silently moving on and entering wrong data into the next field).
    """
    field = page.get_by_label(field_label, exact=False)
    btn = field.locator("xpath=ancestor::tr//button[contains(@class,'DocControlFileButton')]")
    if btn.count() == 0:
        btn = page.locator("button.DocControlFileButton").first

    # Wait for any existing busy overlay before clicking
    _wait_for_busy_overlay(page)
    btn.click()
    print(f"  [lookup] Clicked search button for '{field_label}'")

    # Wait for the modal Search button to appear
    try:
        page.wait_for_selector("button:has-text('Search'):visible", timeout=8_000)
    except PlaywrightTimeoutError:
        raise Exception(f"Search modal did not appear for '{field_label}'")

    # Wait for the modal to fully render (busy overlay gone)
    _wait_for_busy_overlay(page)

    # Fill the search input
    all_visible = page.locator("input[type='text']:visible").all()
    if not all_visible:
        raise Exception(f"No visible text inputs found in search overlay for '{field_label}'")

    search_input = all_visible[-1]
    search_input.fill(search_term)
    print(f"  [lookup] Entered search term {search_term!r}")

    # Wait for busy overlay to clear before clicking Search
    _wait_for_busy_overlay(page)

    # Click the Search button — retry if the overlay intercepts
    search_btn = page.locator("button:has-text('Search'):visible").last
    for attempt in range(3):
        try:
            search_btn.click(timeout=10_000)
            break
        except Exception as e:
            print(f"  [lookup] Search click attempt {attempt + 1} failed: {e}")
            _wait_for_busy_overlay(page)
            time.sleep(1.0)
    else:
        raise Exception(f"Could not click Search button for '{field_label}' after 3 attempts")

    # Wait for results to load
    _wait_for_busy_overlay(page)
    time.sleep(1.5)

    # Click the matching result
    try:
        result = page.locator(f"text={search_term}").first
        result.wait_for(state="visible", timeout=8_000)
        result.click()
    except Exception:
        raise Exception(f"Search result '{search_term}' did not appear for '{field_label}'")

    _wait_for_page_settle(page)
    _wait_for_busy_overlay(page)
    print(f"  [lookup] '{field_label}' = {search_term!r}")


# ---------------------------------------------------------------------------
# Page steps (unchanged from original)
# ---------------------------------------------------------------------------

def _random_delay(low: float = 0.5, high: float = 1.5) -> None:
    """Human-like random delay."""
    import random
    time.sleep(random.uniform(low, high))


def step_navigate(page: Page) -> None:
    import random
    print("\n[STEP 1] Navigating to Alabama DMV TAP portal...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    print(f"  Loaded: {page.url}")

    # Simulate a human reading the page before doing anything
    _random_delay(2.0, 4.0)

    # Scroll around slightly like a human would
    page.mouse.move(random.randint(200, 600), random.randint(200, 400))
    _random_delay(0.5, 1.5)
    page.evaluate("window.scrollBy(0, %d)" % random.randint(50, 150))
    _random_delay(1.0, 2.0)


def step_click_permit_link(page: Page) -> None:
    import random
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
            # Move mouse to the link first, pause, then click
            el = page.locator(sel).first
            box = el.bounding_box()
            if box:
                page.mouse.move(
                    box["x"] + random.randint(5, int(box["width"]) - 5),
                    box["y"] + random.randint(2, int(box["height"]) - 2),
                )
                _random_delay(0.5, 1.2)
            el.click()
            _wait_for_page_settle(page)
            _random_delay(1.5, 3.0)
            print(f"  Clicked: {sel!r}")
            return
        except PlaywrightTimeoutError:
            continue

    print("  [WARN] Could not find the permit link.")
    for link in page.query_selector_all("a"):
        text = link.inner_text().strip()
        if text:
            print(f"    {text!r}")


def _solve_captcha_with_capsolver(page: Page) -> bool:
    """
    Solve reCAPTCHA v2 using CapSolver API.
    Extracts the site key from the page, sends it to CapSolver,
    and injects the token back into the page.
    Returns True if solved, False on failure.
    """
    import capsolver

    api_key = os.getenv("CAPSOLVER_API_KEY")
    if not api_key:
        print("  [CAPTCHA] CAPSOLVER_API_KEY not set in .env")
        return False

    capsolver.api_key = api_key

    # Extract the reCAPTCHA site key from the page
    site_key = page.evaluate("""() => {
        // 1. Try data-sitekey attribute
        const el = document.querySelector('[data-sitekey]');
        if (el) return el.getAttribute('data-sitekey');
        // 2. Try extracting from any reCAPTCHA iframe src (k= parameter)
        const iframes = document.querySelectorAll('iframe[src*="recaptcha"]');
        for (const iframe of iframes) {
            const m = iframe.src.match(/[?&]k=([A-Za-z0-9_-]{40})/);
            if (m) return m[1];
        }
        // 3. Try the reCAPTCHA script tag
        const scripts = document.querySelectorAll('script[src*="recaptcha"]');
        for (const s of scripts) {
            const m = s.src.match(/[?&]render=([A-Za-z0-9_-]{40})/);
            if (m) return m[1];
        }
        return null;
    }""")

    if not site_key:
        print("  [CAPTCHA] Could not find reCAPTCHA site key on page")
        return False

    print(f"  [CAPTCHA] Found site key: {site_key} (length: {len(site_key)})")
    print("  [CAPTCHA] Sending to CapSolver (this may take 10-30s)...")

    try:
        solution = capsolver.solve({
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": page.url,
            "websiteKey": site_key,
        })
        token = solution.get("gRecaptchaResponse", "")
        if not token:
            print("  [CAPTCHA] CapSolver returned empty token")
            return False

        print(f"  [CAPTCHA] Got token ({len(token)} chars), injecting into page...")

        # Inject the token and fire any callbacks
        page.evaluate("""(token) => {
            document.querySelector('#g-recaptcha-response').value = token;
            // Try standard callback from data-callback attribute
            const el = document.querySelector('.g-recaptcha[data-callback]');
            if (el) {
                const fn = el.getAttribute('data-callback');
                if (window[fn]) { window[fn](token); return; }
            }
            // Try reCAPTCHA internal callback
            if (typeof ___grecaptcha_cfg !== 'undefined') {
                const clients = ___grecaptcha_cfg.clients;
                for (const key in clients) {
                    const client = clients[key];
                    for (const p in client) {
                        const val = client[p];
                        if (val && typeof val === 'object') {
                            for (const s in val) {
                                if (val[s] && typeof val[s].callback === 'function') {
                                    val[s].callback(token);
                                    return;
                                }
                            }
                        }
                    }
                }
            }
        }""", token)

        print("  [CAPTCHA] Token injected successfully")
        return True

    except Exception as e:
        print(f"  [CAPTCHA] CapSolver failed: {e}")
        return False


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
# Payment flow (Alabama TAP → NIC USA secure checkout)
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


def _wait(page: Page, ms: int = 1500) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(ms / 1000)


def _click_next_checkout(page: Page, label: str) -> None:
    """Click the Next button on NIC USA secure checkout pages."""
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
        lambda: page.locator('input[type="submit"]').first.click(timeout=3_000),
    ]:
        try:
            attempt()
            print(f'  [CLICK] Next on {label}')
            return
        except Exception:
            continue

    try:
        all_els = page.locator('*').all()
        for el in all_els:
            try:
                if not el.is_visible():
                    continue
                text = el.inner_text().strip()
                if text in ("Next", "Next >", "Next ›"):
                    el.click()
                    print(f'  [CLICK] Next via element with text "{text}"')
                    return
            except Exception:
                continue
    except Exception:
        pass
    raise Exception(f"Could not find Next button on {label}")


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


def step_payment_select_credit_card(page: Page) -> None:
    """On the Alabama payment options page, select the Credit Card radio button then Next."""
    print("\n[PAYMENT 1] Selecting Credit Card payment option...")

    _wait(page, 2000)

    # The page has two radio buttons: "Bank Account" (first) and "Credit Card" (second).
    # We need the SECOND radio button specifically.
    selected = False

    # Try clicking the label text for Credit Card to trigger the radio
    try:
        # Find the radio button that is a sibling/near "Credit Card" text
        cc_label = page.locator('text="Credit Card"').first
        # Click slightly to the left of the label to hit the radio
        cc_label.click(timeout=5_000)
        print('  [CLICK] Credit Card via label text')
        selected = True
    except Exception:
        pass

    if not selected:
        # Try the second radio button directly
        try:
            radios = page.locator('input[type="radio"]').all()
            if len(radios) >= 2:
                radios[1].check()
                print('  [CLICK] Credit Card via second radio button')
                selected = True
            elif len(radios) == 1:
                radios[0].check()
                print('  [CLICK] Credit Card via only radio button')
                selected = True
        except Exception:
            pass

    if not selected:
        raise Exception("Could not find Credit Card payment option")

    _wait(page, 1000)
    click_next(page)
    _wait(page, 2000)
    print("[OK] Credit Card selected")


def step_payment_next_page(page: Page) -> None:
    """Click Next on the intermediate page before signature."""
    print("\n[PAYMENT 2] Clicking Next on intermediate page...")
    _wait(page, 1500)
    click_next(page)
    _wait(page, 2000)
    print("[OK] Advanced past intermediate page")


def step_payment_signature(page: Page) -> None:
    """Enter signature on the signature page."""
    signer = "Michael Caballero"
    print(f'\n[PAYMENT 3] Entering signature: "{signer}"...')

    _wait(page, 1500)

    signed = False
    for sel in [
        'input[name*="Signature" i]', 'input[name*="signature" i]',
        'input[id*="Signature" i]', 'input[id*="signature" i]',
        'input[name*="SignName" i]', 'input[name*="FullName" i]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                loc.fill(signer)
                print(f'  [FILL] Signature: "{signer}" via {sel}')
                signed = True
                break
        except Exception:
            continue

    if not signed:
        for label in ["Signature", "Sign", "Full Name", "Name", "Electronic Signature"]:
            try:
                loc = page.get_by_label(label, exact=False)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.fill(signer)
                    print(f'  [FILL] Signature: "{signer}" via label "{label}"')
                    signed = True
                    break
            except Exception:
                continue

    if not signed:
        inputs = page.locator('input[type="text"]').all()
        for inp in inputs:
            try:
                if inp.is_visible() and not inp.input_value().strip():
                    inp.fill(signer)
                    print(f'  [FILL] Signature: "{signer}" via first empty text input')
                    signed = True
                    break
            except Exception:
                continue

    if not signed:
        print('  [WARN] Could not find signature field')

    # Click "Pay" button (not Next) on this page
    for sel in [
        'button:has-text("Pay")', 'input[value="Pay"]',
        'a:has-text("Pay")', 'button:has-text("pay")',
        'input[type="submit"][value*="Pay"]',
    ]:
        try:
            page.locator(sel).first.click(timeout=8_000)
            print(f'  [CLICK] Pay via {sel}')
            break
        except Exception:
            continue
    else:
        click_next(page)

    _wait(page, 3000)
    print("[OK] Signature entered, proceeding to checkout")


def step_checkout_fill_customer(page: Page) -> None:
    """Fill customer info on the NIC USA secure checkout page, then click Next."""
    print("\n[PAYMENT 4] Filling checkout customer info...")
    print(f"  [INFO] Current URL: {page.url}")

    _wait(page, 5000)

    # Auto-accept any JS dialogs on this page
    page.on("dialog", lambda dialog: dialog.accept())

    # Fill customer fields by label
    field_map = [
        ("First Name",    CHECKOUT_CUSTOMER["first_name"]),
        ("Last Name",     CHECKOUT_CUSTOMER["last_name"]),
        ("Address",       CHECKOUT_CUSTOMER["address"]),
        ("City",          CHECKOUT_CUSTOMER["city"]),
        ("ZIP",           CHECKOUT_CUSTOMER["zip"]),
        ("Zip",           CHECKOUT_CUSTOMER["zip"]),
        ("Phone",         CHECKOUT_CUSTOMER["phone"]),
        ("Email",         CHECKOUT_CUSTOMER["email"]),
    ]
    for label, value in field_map:
        try:
            loc = page.get_by_label(label, exact=False)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.fill("")
                loc.first.fill(value)
                print(f'  [FILL] {label}: "{value}"')
        except Exception:
            pass

    # Country dropdown
    for sel in ['select[name*="Country" i]', 'select[id*="Country" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                opts = loc.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                for o in opts:
                    if "united states" in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] Country: "{o["text"]}"')
                        break
                break
        except Exception:
            continue

    # State dropdown
    for sel in ['select[name*="State" i]', 'select[id*="State" i]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                opts = loc.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                target = CHECKOUT_CUSTOMER["state"].lower()
                for o in opts:
                    if target in o["text"].lower() or "florida" in o["text"].lower():
                        loc.select_option(value=o["value"])
                        print(f'  [SELECT] State: "{o["text"]}"')
                        break
                break
        except Exception:
            continue

    _wait(page, 1000)
    _click_next_checkout(page, "customer info")
    _wait(page, 3000)
    print("[OK] Customer info filled")


def step_checkout_fill_card(page: Page, payment_card: dict) -> None:
    """Fill credit card details on the NIC USA payment info page."""
    print("\n[PAYMENT 5] Filling payment card info...")

    _wait(page, 2000)

    target_frame = page
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
                        target_frame = frame
                        card_found = True
                        print(f'  [INFO] Card fields in iframe: {frame.url[:60]}')
                        break
                if card_found:
                    break
            except Exception:
                continue

    _fill_payment_field(target_frame, [
        'input[name*="CardNumber" i]', 'input[id*="CardNumber" i]',
        'input[name*="ccNumber" i]', 'input[name*="card_number" i]',
        'input[autocomplete="cc-number"]',
    ], payment_card["cardNumber"], "Card Number")

    _select_payment_field(target_frame, [
        'select[name*="ExpMonth" i]', 'select[id*="ExpMonth" i]',
        'select[name*="ExpirationMonth" i]', 'select[name*="ccMonth" i]',
        'select[autocomplete="cc-exp-month"]',
    ], payment_card["expMonth"], "Expiration Month")

    _select_payment_field(target_frame, [
        'select[name*="ExpYear" i]', 'select[id*="ExpYear" i]',
        'select[name*="ExpirationYear" i]', 'select[name*="ccYear" i]',
        'select[autocomplete="cc-exp-year"]',
    ], payment_card["expYear"], "Expiration Year")

    _fill_payment_field(target_frame, [
        'input[name*="SecurityCode" i]', 'input[name*="CVV" i]',
        'input[name*="CVC" i]', 'input[name*="CardCode" i]',
        'input[id*="SecurityCode" i]', 'input[id*="CVV" i]',
        'input[autocomplete="cc-csc"]',
    ], payment_card["cvv"], "Security Code")

    _fill_payment_field(target_frame, [
        'input[name*="NameOnCard" i]', 'input[name*="CardName" i]',
        'input[name*="cardHolder" i]', 'input[id*="NameOnCard" i]',
        'input[autocomplete="cc-name"]',
    ], payment_card["cardholderName"], "Name on Card")

    print("[OK] Card info filled")


def step_checkout_submit(page: Page) -> None:
    """Click Next on card page, then Submit Payment."""
    print("\n[PAYMENT 6] Submitting payment...")

    _click_next_checkout(page, "payment info page")
    _wait(page, 3000)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _wait(page, 1000)

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

    _wait(page, 5000)
    print("[OK] Payment submitted")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(permit: dict, job_id: str, on_captcha_needed: Optional[Callable] = None, company: dict = None, payment_card: dict = None) -> dict:
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

    if not payment_card or not payment_card.get("cardNumber"):
        return {
            "permitId": permit_id, "driverName": driver_name,
            "tractor": tractor, "permitType": permit_type,
            "status": "error", "message": "No payment card configured — go to Settings to add a card",
        }

    # Build the flat form data dict from permit + company constants
    data = build_form_data(permit, COMPANY)
    print(f"[Alabama] Starting permit {permit_id} for {driver_name} ({tractor})")

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

        # Auto-accept JS alert/confirm dialogs
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            step_navigate(page)
            step_click_permit_link(page)

            # --- CAPTCHA via CapSolver ---
            print("\n[STEP 3] About / intro page — CAPTCHA required.")
            debug_fields(page)

            solved = _solve_captcha_with_capsolver(page)
            if not solved:
                print("  [CAPTCHA] CapSolver failed — waiting for manual solve")
                if on_captcha_needed:
                    on_captcha_needed()
                timeout_s = 300
                start = time.time()
                while time.time() - start < timeout_s:
                    try:
                        token = page.evaluate(
                            "() => document.querySelector('#g-recaptcha-response')?.value || ''"
                        )
                        if token:
                            print("  [OK] CAPTCHA solved manually")
                            solved = True
                            break
                    except Exception:
                        pass
                    time.sleep(1)

            if not solved:
                print("  [WARN] CAPTCHA not solved — attempting to continue anyway")

            time.sleep(1)
            click_next(page)

            # --- Form filling ---
            step_page1_identification(page, data)
            step_page2_mailing_address(page, data)
            step_page3_vehicle_details(page, data)

            # --- Payment flow ---
            step_payment_select_credit_card(page)
            step_payment_next_page(page)
            step_payment_signature(page)
            step_checkout_fill_customer(page)
            step_checkout_fill_card(page, payment_card)
            step_checkout_submit(page)

            return {
                "permitId": permit_id, "driverName": driver_name,
                "tractor": tractor, "permitType": permit_type,
                "status": "success", "message": "Payment submitted",
            }

        except Exception as e:
            print(f"\n[Alabama] Error for {driver_name}: {e}")
            return {
                "permitId": permit_id, "driverName": driver_name,
                "tractor": tractor, "permitType": permit_type,
                "status": "error", "message": str(e),
            }
        finally:
            time.sleep(3)
            try:
                browser.close()
            except Exception:
                pass
