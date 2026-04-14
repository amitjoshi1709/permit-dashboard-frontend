"""
Florida DOT Portal — Trip Permit Automation (pas.fdot.gov)

Flow:
  1. Login
  2. Create Application
  3. Fill permittee contact info (company name, address, email, phone)
  4. Check "Is invoice same as permittee?"
  5. Verify address → Continue
  6. Select Trip permit type, effective date
  7. Click New Vehicle → page renders vehicle config, dimensions, axles
  8. Fill all vehicle/load fields from extraFields
  9. Save → Routing → mark success

Data flow:
  Backend builds permit dict (driver details from Supabase + company from config.py)
  → extraFields dict carries all FL-specific form values from the frontend
  → Runner logs in, fills pages, stops at routing (success)
"""

import os
import time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORTAL_URL = "https://pas.fdot.gov/Account.aspx/LogOn?ReturnUrl=%2fHome.aspx%2fBase"
SLOW_MO = 120
TIMEOUT = 30_000
FILL_RETRIES = 4          # attempts per field
FILL_SETTLE_MS = 250      # wait between fill and verify (KO async)

# Permit type → top-of-page radio id (from earlier debug dumps).
#   "800"=Blanket, "801"=Trip, "803"=Route Specific Blanket, "804"=Vehicle Specific Blanket
PERMIT_TYPE_RADIO_ID = {
    "trip":                     "801",
    "fuel":                     "801",
    "trip_fuel":                "801",
    "fl_blanket_bulk":          "800",
    "fl_blanket_inner_bridge":  "800",
    "fl_blanket_flatbed":       "800",
}

# Inner Bridge: exact label of the option in #VehicleConfigurationCode dropdown.
# TODO: confirm via _dump_page_fields on first run with Blanket radio selected.
# The dump from the Trip flow did not include this option, so this is a placeholder
# that the runner will substring-match against the live dropdown options.
FL_INNER_BRIDGE_VEHICLE_CONFIG = "Inner Bridge"

# Blanket Flatbed: first option in FL's load-description dropdown is the long
# "construction or industrial material / equipment / prefabricated structural item"
# entry. The runner picks it by index 1 (skipping the "Select ..." placeholder)
# rather than by exact text, so future portal copy changes don't break us.
FL_FLATBED_LOAD_DESC_OPTION_INDEX = 1
# Exact portal text for the "Construction" option in FL's load-description dropdown.
FL_CONSTRUCTION_LOAD_DESC = "Construction Or Industrial Material/Equipment Or Prefabricated Structural Item"


def _compute_flatbed_begin_date(now: Optional[datetime] = None) -> str:
    """Return MM/DD/YYYY: +2 work days from `now` if before 4 PM local, else +3.
    Mon\u2013Fri only; weekends are skipped. No holiday calendar."""
    now = now or datetime.now()
    add = 2 if now.time() < dtime(16, 0) else 3
    d = now.date()
    while add > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon=0..Fri=4
            add -= 1
    return d.strftime("%m/%d/%Y")


# ---------------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------------

class PermitError(Exception):
    def __init__(self, message: str, screenshot_path: str = None):
        super().__init__(message)
        self.screenshot_path = screenshot_path


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
# Low-level helpers
# ---------------------------------------------------------------------------

def _fatal(page: Page, message: str):
    """Take error screenshot then raise PermitError."""
    print(f"\n  [FATAL] {message}")
    err_screenshot = None
    try:
        err_screenshot = os.path.join(_screenshot_dir, f"ERROR_{int(time.time() * 1000)}.png")
        page.screenshot(path=err_screenshot, full_page=True)
        print(f"  [FATAL] Error screenshot saved: {err_screenshot}")
    except Exception as e:
        print(f"  [FATAL] Could not save error screenshot: {e}")
    raise PermitError(message, err_screenshot)


def _normalize(v: str) -> str:
    """Strip whitespace, commas, and the ft/in quote chars so formatter rewrites don't trip equality.
    The FL portal's KO formatter adds commas to numeric fields (e.g. 15200 → '15,200')
    and foot/inch symbols to dimensions. We strip all of these before comparing."""
    return (v or "").strip().replace(",", "").replace("'", "").replace('"', "").replace(" ", "")


def _safe_fill(page: Page, selector: str, value: str, field_name: str, strict: bool = False):
    """Fill a text input with retry-until-verified semantics.

    FL's Knockout formatters are async — the value may not appear in the DOM for several
    hundred ms after fill(). Rather than a single read-back (which races the formatter),
    we loop: fill → Tab → wait FILL_SETTLE_MS → read → if empty/mismatch, retry. This
    eliminates the race where a field logs ✓ but is actually blank on screen.
    """
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Selector not found for "{field_name}": {selector}')

    last_actual = ""
    for attempt in range(1, FILL_RETRIES + 1):
        try:
            locator.click(click_count=3)
            locator.fill("")
            locator.fill(value)
            try:
                locator.press("Tab")
            except Exception:
                pass
        except Exception as e:
            print(f'  [WARN] {field_name} fill attempt {attempt} raised: {e}')

        page.wait_for_timeout(FILL_SETTLE_MS)

        try:
            last_actual = locator.input_value()
        except Exception:
            last_actual = ""

        if _normalize(last_actual) == _normalize(value):
            print(f'  [FILL] {field_name}: "{value}" \u2713 (attempt {attempt})')
            return

        print(f'  [RETRY {attempt}/{FILL_RETRIES}] {field_name} — wanted "{value}" got "{last_actual}"')

    # Out of attempts
    if strict:
        _fatal(page, f'Value mismatch on "{field_name}" after {FILL_RETRIES} attempts. Expected: "{value}", Got: "{last_actual}"')
    print(f'  [WARN] {field_name} never committed after {FILL_RETRIES} attempts — last value "{last_actual}" (continuing)')


def _safe_select(page: Page, selector: str, value: str, field_name: str):
    """Select a dropdown option by value or label."""
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Dropdown not found for "{field_name}": {selector}')

    # Try by value first, then by label
    try:
        locator.select_option(value=value)
    except Exception:
        try:
            locator.select_option(label=value)
        except Exception as e:
            _fatal(page, f'Dropdown option not found for "{field_name}": "{value}". Error: {e}')

    print(f'  [SELECT] {field_name}: "{value}" \u2713')


def _safe_click(page: Page, selector: str, field_name: str, timeout: int = 5000):
    """Click an element with error handling."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.locator(selector).first.click()
        print(f'  [CLICK] {field_name} \u2713')
    except PlaywrightTimeoutError:
        _fatal(page, f'Element not found for click "{field_name}": {selector}')


def _safe_check(page: Page, selector: str, field_name: str):
    """Check a checkbox if not already checked."""
    try:
        page.wait_for_selector(selector, timeout=5000)
        locator = page.locator(selector).first
    except PlaywrightTimeoutError:
        _fatal(page, f'Checkbox not found for "{field_name}": {selector}')

    if not locator.is_checked():
        locator.click()
        print(f'  [CHECK] {field_name} \u2713')
    else:
        print(f'  [OK] {field_name} already checked \u2713')


# ---------------------------------------------------------------------------
# Page 1: Login
# ---------------------------------------------------------------------------

def _login(page: Page, username: str, password: str):
    """Log into the Florida DOT portal."""
    print("\n[ACT] Logging into Florida DOT portal...")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    _screenshot(page, "login_page")

    # Fill username and password
    user_sel = 'input[name="UserName"], input#UserName'
    pass_sel = 'input[name="Password"], input#Password, input[type="password"]'
    _safe_fill(page, user_sel, username, "Username")
    _safe_fill(page, pass_sel, password, "Password")

    # Pre-submit verification: the FL portal has an onload JS that sometimes clears
    # the form after our initial fill. Re-read both fields and re-fill if either is
    # empty/mismatched before clicking Login. (Observed: job 3 of 3 in a batch hit this
    # and submitted an empty form, bouncing back to LogOn.)
    for guard_pass in range(1, 4):
        try:
            u_actual = page.locator(user_sel).first.input_value()
            p_actual = page.locator(pass_sel).first.input_value()
        except Exception:
            u_actual = p_actual = ""
        if u_actual == username and p_actual == password:
            break
        print(f"  [LOGIN-GUARD pass {guard_pass}] Fields drifted (user={'Y' if u_actual else 'N'} pass={'Y' if p_actual else 'N'}) — re-filling")
        if u_actual != username:
            _safe_fill(page, user_sel, username, "Username [re-fill]")
        if p_actual != password:
            _safe_fill(page, pass_sel, password, "Password [re-fill]")
        page.wait_for_timeout(400)
    else:
        _fatal(page, "Login fields kept clearing after 3 re-fill attempts")

    # Click login button
    page.locator('input[type="submit"], button[type="submit"]').first.click()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        pass

    # Wait for the portal to fully transition away from the login page.
    # The FL portal can be very slow after login — wait up to 45 seconds for
    # the URL to stop containing "LogOn"/"Login".
    for wait_pass in range(1, 16):
        if "LogOn" not in page.url and "Login" not in page.url:
            break
        print(f"  [LOGIN-WAIT] Still on login page... ({wait_pass * 3}s)")
        page.wait_for_timeout(3000)
    else:
        _fatal(page, "Login failed — still on login page after 45s. Check FL credentials or portal may be down.")

    _screenshot(page, "login_success")
    print("[OK] Login successful")

    # Wait for the post-login dashboard to fully render before proceeding.
    # The FL portal can take several seconds after the URL changes before the
    # main page content (e.g., "Create Application" link) is actually present.
    print("  [POST-LOGIN] Waiting for dashboard to stabilize...")
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    _screenshot(page, "post_login_dashboard")
    print("  [POST-LOGIN] Dashboard ready")


# ---------------------------------------------------------------------------
# Page 2: Create Application → Permittee Contact Info
# ---------------------------------------------------------------------------

def _create_application(page: Page):
    """Click Create Application to start a new permit."""
    print("\n[ACT] Clicking Create Application...")

    # The dashboard may still be loading — retry finding the button for up to 30s.
    create_btn = None
    for attempt in range(1, 11):
        try:
            btn = page.get_by_role("link", name="Create Application")
            if btn.count() == 0:
                btn = page.get_by_role("button", name="Create Application")
            if btn.count() == 0:
                btn = page.locator("a:has-text('Create Application'), button:has-text('Create Application')")
            if btn.count() > 0:
                create_btn = btn
                break
        except Exception:
            pass
        print(f"  [CREATE-APP] Button not found yet... ({attempt * 3}s)")
        page.wait_for_timeout(3000)

    if not create_btn:
        _fatal(page, "Could not find Create Application button after 30s")

    try:
        create_btn.first.click(timeout=10000)
    except Exception as e:
        _fatal(page, f"Could not click Create Application: {e}")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)
    _screenshot(page, "create_application_clicked")
    print("[OK] Create Application page loaded")


def _fill_permittee_info(page: Page, company: dict, phone: str):
    """
    Fill the permittee contact info page:
    Name, address, country, city, state, zip, email, phone.
    Check 'is invoice same as permittee?'
    Verify address → Continue.
    """
    print("\n[ACT] Filling permittee contact info...")

    # Company / permittee name — required field, try multiple selectors
    name_filled = False
    name_selectors = [
        'input[name*="PermitteeName"]',
        'input[id*="PermitteeName"]',
        'input[name*="CompanyName"]',
        'input[id*="CompanyName"]',
        'input[name*="Permitee"]',
        'input[id*="Permitee"]',
    ]
    for sel in name_selectors:
        try:
            page.wait_for_selector(sel, timeout=2000)
            _safe_fill(page, sel, company["legal_name"], "Permittee Name")
            name_filled = True
            break
        except PlaywrightTimeoutError:
            continue

    if not name_filled:
        # Last resort — find the first visible text input on the page
        try:
            first_input = page.locator('input[type="text"]:visible').first
            first_input.fill(company["legal_name"])
            print(f'  [FILL] Permittee Name (first text input fallback): "{company["legal_name"]}" \u2713')
        except Exception:
            _fatal(page, "Could not find Permittee Name field on contact info page")

    # Address
    addr_selectors = [
        ('input[name*="Address"], input[name*="Street"], input[id*="Address"], input[id*="Street"]', company["street"], "Street Address"),
        ('input[name*="City"], input[id*="City"]', company["city"], "City"),
        ('input[name*="Zip"], input[name*="PostalCode"], input[id*="Zip"]', company["zip"], "Zip Code"),
    ]

    for sel, val, label in addr_selectors:
        try:
            page.wait_for_selector(sel, timeout=3000)
            _safe_fill(page, sel, val, label)
        except PlaywrightTimeoutError:
            print(f"  [WARN] {label} field not found — may be pre-filled or different selector")

    # State dropdown
    state_sel = 'select[name*="State"], select[id*="State"]'
    try:
        page.wait_for_selector(state_sel, timeout=3000)
        _safe_select(page, state_sel, company["state"], "State")
    except PlaywrightTimeoutError:
        print("  [WARN] State dropdown not found")

    # Country
    country_sel = 'select[name*="Country"], select[id*="Country"]'
    try:
        page.wait_for_selector(country_sel, timeout=3000)
        _safe_select(page, country_sel, "US", "Country")
    except PlaywrightTimeoutError:
        print("  [WARN] Country dropdown not found")

    # Email
    email_sel = 'input[name*="Email"], input[id*="Email"], input[type="email"]'
    try:
        page.wait_for_selector(email_sel, timeout=3000)
        _safe_fill(page, email_sel, company["primary_email"], "Email")
    except PlaywrightTimeoutError:
        print("  [WARN] Email field not found")

    # Phone
    phone_sel = 'input[name*="Phone"], input[id*="Phone"], input[type="tel"]'
    try:
        page.wait_for_selector(phone_sel, timeout=3000)
        _safe_fill(page, phone_sel, phone, "Phone")
    except PlaywrightTimeoutError:
        print("  [WARN] Phone field not found")

    _screenshot(page, "permittee_info_filled")

    # Check "Is invoice same as permittee?"
    print("\n[ACT] Checking 'Is invoice same as permittee?'...")
    invoice_check_sel = 'input[name*="InvoiceSame"], input[name*="invoice"], input[id*="InvoiceSame"], input[type="checkbox"]'
    try:
        checkboxes = page.locator(invoice_check_sel)
        # Find the one related to invoice
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            parent_text = cb.evaluate("el => el.closest('label, div, span')?.textContent || ''").lower()
            if "invoice" in parent_text or "same" in parent_text:
                if not cb.is_checked():
                    cb.click()
                    print('  [CHECK] "Is invoice same as permittee?" \u2713')
                else:
                    print('  [OK] Invoice checkbox already checked \u2713')
                break
        else:
            # If no match by text, just check the first checkbox near "invoice"
            invoice_area = page.locator('text=invoice').first
            if invoice_area.count() > 0:
                nearby_cb = invoice_area.locator("xpath=ancestor::*[3]//input[@type='checkbox']").first
                if not nearby_cb.is_checked():
                    nearby_cb.click()
                    print('  [CHECK] Invoice checkbox (nearby match) \u2713')
    except Exception as e:
        print(f"  [WARN] Could not find invoice checkbox: {e}")

    _screenshot(page, "invoice_checkbox_checked")

    # Verify Address button
    print("\n[ACT] Clicking Verify Address...")
    try:
        verify_btn = page.locator('button:has-text("Verify"), input[value*="Verify"], a:has-text("Verify Address")')
        if verify_btn.count() > 0:
            verify_btn.first.click()
            page.wait_for_timeout(3000)
            _screenshot(page, "address_verified")
            print("  [OK] Address verified")
        else:
            print("  [WARN] Verify Address button not found — skipping")
    except Exception as e:
        print(f"  [WARN] Verify Address error: {e}")

    # Continue button
    print("\n[ACT] Clicking Continue...")
    try:
        continue_btn = page.locator('button:has-text("Continue"), input[value*="Continue"], a:has-text("Continue")')
        continue_btn.first.click(timeout=5000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception as e:
        _fatal(page, f"Could not click Continue after permittee info: {e}")

    _screenshot(page, "permittee_continue")
    print("[OK] Permittee page complete — moved to permit details")


# ---------------------------------------------------------------------------
# Page 3: Permit Details — type, dates, vehicle, load fields
# ---------------------------------------------------------------------------

def _fill_permit_type_and_dates(page: Page, permit_type: str, effective_date: str):
    """
    Select the permit type radio (Trip / Blanket / etc.) and fill travel dates.

    Permit type radios on the FL portal (ids confirmed via earlier debug dumps):
      800=Blanket, 801=Trip, 803=Route Specific Blanket, 804=Vehicle Specific Blanket

    For `fl_blanket_flatbed`, the caller must pass an already-computed effective_date
    (via _compute_flatbed_begin_date) — this function does not compute dates itself.
    """
    print("\n[ACT] Selecting permit type and dates...")

    radio_id = PERMIT_TYPE_RADIO_ID.get(permit_type, "801")  # default Trip
    radio_label = {
        "800": "Blanket",
        "801": "Trip",
        "803": "Route Specific Blanket",
        "804": "Vehicle Specific Blanket",
    }.get(radio_id, radio_id)

    # Click the radio by exact id (much more reliable than label/value text matching)
    try:
        sel = f'input[type="radio"][id="{radio_id}"]'
        page.wait_for_selector(sel, timeout=5000)
        page.locator(sel).first.click()
        print(f'  [SELECT] Permit Type radio: "{radio_label}" (id={radio_id}, permit_type={permit_type}) \u2713')
    except PlaywrightTimeoutError:
        _fatal(page, f"Could not find permit type radio id={radio_id} for {permit_type}")
    except Exception as e:
        _fatal(page, f"Error clicking permit type radio for {permit_type}: {e}")

    page.wait_for_timeout(2000)

    # Travel Begin Date
    begin_date_sel = 'input[name*="BeginDate"], input[name*="TravelBegin"], input[id*="BeginDate"], input[id*="TravelBegin"]'
    try:
        page.wait_for_selector(begin_date_sel, timeout=5000)
        date_field = page.locator(begin_date_sel).first
        date_field.click(click_count=3)
        date_field.fill(effective_date)
        date_field.press("Tab")
        page.wait_for_timeout(1000)
        print(f'  [FILL] Travel Begin Date: "{effective_date}" \u2713')
    except PlaywrightTimeoutError:
        print(f"  [WARN] Travel Begin Date field not found — may auto-fill")

    # Travel End Date auto-fills — just log it
    end_date_sel = 'input[name*="EndDate"], input[name*="TravelEnd"], input[id*="EndDate"], input[id*="TravelEnd"]'
    try:
        page.wait_for_selector(end_date_sel, timeout=3000)
        end_val = page.locator(end_date_sel).first.input_value()
        if end_val:
            print(f'  [AUTO] Travel End Date: "{end_val}"')
    except PlaywrightTimeoutError:
        pass

    _screenshot(page, "permit_type_selected")
    print("[OK] Permit type and dates set")


def _select_new_vehicle(page: Page):
    """
    Select 'New Vehicle' from the 'Select Profile Vehicle' dropdown.
    This renders all vehicle/load fields on the same page.
    """
    print("\n[ACT] Selecting 'New Vehicle' from Profile Vehicle dropdown...")

    # Find the Select Profile Vehicle dropdown and select "New Vehicle"
    # Must trigger all native browser events so the portal's JS framework renders fields
    try:
        all_selects = page.locator('select')
        found = False
        for i in range(all_selects.count()):
            dd = all_selects.nth(i)
            options_text = dd.evaluate("""el => {
                return Array.from(el.options).map(o => ({value: o.value, text: o.text}))
            }""")
            new_veh_opt = None
            for opt in options_text:
                if "new vehicle" in opt["text"].lower():
                    new_veh_opt = opt
                    break
            if new_veh_opt:
                # Simulate real user interaction to fire all JS events
                dd.evaluate("""(el, targetValue) => {
                    // Focus the element
                    el.focus();
                    el.dispatchEvent(new Event('focus', {bubbles: true}));

                    // Set the value
                    el.value = targetValue;

                    // Fire every event a real user would trigger
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));

                    // Knockout.js specific — trigger valueChanged
                    if (typeof ko !== 'undefined') {
                        ko.utils.triggerEvent(el, 'change');
                    }

                    // jQuery specific
                    if (typeof jQuery !== 'undefined') {
                        jQuery(el).trigger('change');
                    }
                    if (typeof $ !== 'undefined' && $.fn) {
                        $(el).trigger('change');
                    }

                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                }""", new_veh_opt["value"])

                print(f'  [SELECT] Profile Vehicle: "{new_veh_opt["text"]}" \u2713')
                found = True
                break

        if not found:
            _fatal(page, "Could not find 'New Vehicle' option in any dropdown")

    except PermitError:
        raise
    except Exception as e:
        _fatal(page, f"Error selecting New Vehicle: {e}")

    # Wait for JS to render the vehicle/load fields
    print("  [WAIT] Waiting for vehicle fields to render...")
    page.wait_for_timeout(5000)

    # Verify fields actually rendered — check if there are more inputs now
    field_count = page.locator('input:visible, select:visible, textarea:visible').count()
    print(f"  [DEBUG] Visible form fields after wait: {field_count}")

    _screenshot(page, "new_vehicle_selected")

    if field_count < 10:
        print("  [WARN] Few fields detected — trying click-based approach...")
        # Fallback: physically click the dropdown and the option
        all_selects = page.locator('select')
        for i in range(all_selects.count()):
            dd = all_selects.nth(i)
            options_text = dd.evaluate("el => Array.from(el.options).map(o => o.text)")
            if any("new vehicle" in t.lower() for t in options_text):
                # Click to open, select by keyboard
                dd.click()
                page.wait_for_timeout(500)
                dd.select_option(label=[t for t in options_text if "new vehicle" in t.lower()][0])
                dd.press("Tab")
                page.wait_for_timeout(5000)

                field_count = page.locator('input:visible, select:visible, textarea:visible').count()
                print(f"  [DEBUG] Fields after click fallback: {field_count}")
                _screenshot(page, "new_vehicle_fallback")
                break

    print("[OK] New Vehicle selected — vehicle/load fields rendered")




def _dump_page_fields(page: Page):
    """
    Debug: dump every visible input, select, and textarea on the page.
    Returns a list of dicts with tag, type, id, name, and visible label text.
    """
    fields = page.evaluate("""() => {
        const results = [];
        const els = document.querySelectorAll('input, select, textarea');
        for (const el of els) {
            // Skip hidden fields
            if (el.type === 'hidden') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;

            // Try to find a label
            let label = '';
            if (el.id) {
                const lbl = document.querySelector('label[for="' + el.id + '"]');
                if (lbl) label = lbl.textContent.trim();
            }
            if (!label) {
                const parent = el.closest('td, div, label, span');
                if (parent) {
                    const prev = parent.previousElementSibling;
                    if (prev) label = prev.textContent.trim().substring(0, 80);
                }
            }

            let options = [];
            if (el.tagName === 'SELECT') {
                options = Array.from(el.options).map(o => o.text.trim()).slice(0, 10);
            }

            results.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                id: el.id || '',
                name: el.name || '',
                value: el.value || '',
                label: label,
                options: options,
            });
        }
        return results;
    }""")

    print(f"\n  [DEBUG] ═══ Page fields dump ({len(fields)} visible fields) ═══")
    for f in fields:
        opts = f" options={f['options']}" if f['options'] else ""
        val = f" value=\"{f['value']}\"" if f['value'] else ""
        print(f"  [DEBUG]  {f['tag']}  type={f['type']}  id=\"{f['id']}\"  name=\"{f['name']}\"  label=\"{f['label']}\"{val}{opts}")
    print(f"  [DEBUG] ═══ End dump ═══\n")
    return fields


def _parse_ft_in(val) -> tuple[str, str]:
    """Accept either {'ft':..,'in':..} or a string like "10'6\"" and return ('ft','in')."""
    if isinstance(val, dict):
        return (str(val.get("ft") or "0"), str(val.get("in") or "0"))
    if isinstance(val, (int, float)):
        return (str(val), "0")
    s = str(val or "").strip().replace('"', "")
    if "'" in s:
        ft, _, inch = s.partition("'")
        return (ft.strip() or "0", inch.strip() or "0")
    return (s or "0", "0")


def _ko_fill(page: Page, selector: str, value: str, field_name: str):
    """Set a text input's value through JS and fire focus/input/change/blur.
    Used when Playwright's .fill() is blocked by a KO formatter/mask."""
    try:
        page.wait_for_selector(selector, timeout=5000)
    except PlaywrightTimeoutError:
        print(f'  [WARN] {field_name} selector not found: {selector}')
        return False
    ok = page.evaluate(
        """({sel, val}) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            el.focus();
            el.dispatchEvent(new Event('focus', {bubbles:true}));
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            if (typeof jQuery !== 'undefined') { jQuery(el).trigger('change'); }
            el.dispatchEvent(new Event('blur', {bubbles:true}));
            return true;
        }""",
        {"sel": selector, "val": str(value)},
    )
    if ok:
        print(f'  [KO-FILL] {field_name}: "{value}" \u2713')
    return ok


def _find_input_by_label(page: Page, label_text: str):
    """Return a CSS selector for an input whose visible label (or adjacent text) contains label_text.
    Uses JS DOM walk. Returns None if not found."""
    result = page.evaluate(
        """(needle) => {
            const target = needle.toLowerCase();
            // 1. <label for="id"> match
            for (const lbl of document.querySelectorAll('label')) {
                if ((lbl.textContent || '').toLowerCase().includes(target)) {
                    const forId = lbl.getAttribute('for');
                    if (forId) {
                        const el = document.getElementById(forId);
                        if (el && (el.tagName === 'INPUT' || el.tagName === 'SELECT')) {
                            return '#' + CSS.escape(forId);
                        }
                    }
                    // Nested input
                    const nested = lbl.querySelector('input, select');
                    if (nested) {
                        if (nested.id) return '#' + CSS.escape(nested.id);
                    }
                }
            }
            // 2. Walk all inputs; check previous sibling / parent text
            for (const el of document.querySelectorAll('input, select')) {
                if (el.type === 'hidden') continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
                let ctx = '';
                if (el.previousElementSibling) ctx += (el.previousElementSibling.textContent || '');
                const parent = el.closest('td, div, span, label');
                if (parent) ctx += ' ' + (parent.textContent || '');
                if (ctx.toLowerCase().includes(target)) {
                    if (el.id) return '#' + CSS.escape(el.id);
                    if (el.name) return '[name="' + el.name + '"]';
                }
            }
            return null;
        }""",
        label_text,
    )
    return result


def _ko_select(page: Page, selector: str, desired_label: str, field_name: str):
    """Select an option in a Knockout-bound <select> by visible text (case-insensitive),
    then fire focus/input/change/blur so KO's valueAccessor commits."""
    try:
        page.wait_for_selector(selector, timeout=5000)
    except PlaywrightTimeoutError:
        _fatal(page, f'Dropdown not found for "{field_name}": {selector}')

    result = page.evaluate(
        """({sel, desired}) => {
            const el = document.querySelector(sel);
            if (!el) return {ok:false, err:'not_found'};
            const target = desired.trim().toLowerCase();
            let matched = null;
            for (const o of el.options) {
                if ((o.text || '').trim().toLowerCase() === target) { matched = o; break; }
            }
            if (!matched) {
                // Fallback: contains
                for (const o of el.options) {
                    if ((o.text || '').trim().toLowerCase().includes(target)) { matched = o; break; }
                }
            }
            if (!matched) return {ok:false, err:'no_option', options: Array.from(el.options).map(o=>o.text)};
            el.focus();
            el.dispatchEvent(new Event('focus', {bubbles:true}));
            el.value = matched.value;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            if (typeof jQuery !== 'undefined') { jQuery(el).trigger('change'); }
            el.dispatchEvent(new Event('blur', {bubbles:true}));
            return {ok:true, text: matched.text, value: matched.value};
        }""",
        {"sel": selector, "desired": desired_label},
    )
    if not result.get("ok"):
        _fatal(page, f'Could not select "{desired_label}" in {field_name}: {result}')
    print(f'  [SELECT] {field_name}: "{result["text"]}" \u2713')


def _debug_probe(page: Page):
    """Targeted diagnostics for Total Width and Axle Count."""
    info = page.evaluate(
        """() => {
            const out = {};
            // Width ft
            const w = document.querySelector('#TotalWidthFeet');
            if (w) {
                out.width_ft = {
                    outerHTML: w.outerHTML,
                    readOnly: w.readOnly,
                    disabled: w.disabled,
                    maxLength: w.maxLength,
                    type: w.type,
                    value: w.value,
                    dataBind: w.getAttribute('data-bind') || '',
                    parentHTML: (w.parentElement && w.parentElement.outerHTML || '').slice(0, 400),
                    count: document.querySelectorAll('#TotalWidthFeet').length,
                };
            } else {
                out.width_ft = 'NOT FOUND';
            }
            // Find candidates for axle count: any heading/label containing "axle"
            const axleCtx = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            const seenParents = new Set();
            while ((node = walker.nextNode())) {
                const txt = (node.textContent || '').trim().toLowerCase();
                if (!txt) continue;
                if (txt.includes('number of axle') || txt.includes('# axle') || txt.includes('axles:') || (txt === 'axles')) {
                    let p = node.parentElement;
                    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
                        if (seenParents.has(p)) break;
                        seenParents.add(p);
                        const inputs = p.querySelectorAll('input, select');
                        if (inputs.length > 0) {
                            axleCtx.push({
                                text: txt.slice(0, 80),
                                container: p.tagName + (p.id ? '#' + p.id : '') + (p.className ? '.' + p.className.split(' ').join('.') : ''),
                                containerHTML: p.outerHTML.slice(0, 600),
                                inputs: Array.from(inputs).map(el => ({
                                    tag: el.tagName,
                                    type: el.type || '',
                                    id: el.id || '',
                                    name: el.name || '',
                                    value: el.value || '',
                                    dataBind: el.getAttribute('data-bind') || '',
                                })),
                            });
                            break;
                        }
                    }
                }
            }
            out.axle_contexts = axleCtx.slice(0, 5);

            // Also: every input with data-bind containing "Axle" or "Number"
            const dbInputs = [];
            for (const el of document.querySelectorAll('input, select')) {
                const db = el.getAttribute('data-bind') || '';
                if (/axle|numberof/i.test(db)) {
                    dbInputs.push({
                        tag: el.tagName,
                        id: el.id || '',
                        name: el.name || '',
                        value: el.value || '',
                        dataBind: db.slice(0, 200),
                    });
                }
            }
            out.axle_databind_inputs = dbInputs;
            return out;
        }"""
    )
    print("\n  [PROBE] ═══ Width/Axle diagnostics ═══")
    import json as _json
    print("  [PROBE] " + _json.dumps(info, indent=2).replace("\n", "\n  [PROBE] "))
    print("  [PROBE] ═══ End diagnostics ═══\n")


def _fill_vehicle_and_load(page: Page, permit: dict, extra: dict, permit_type: str = "trip"):
    """
    Fill the Florida vehicle/load/dimensions/axles page using explicit element ids
    observed on the live FL portal. No fuzzy matching — every field has a known id.
    """
    print("\n[ACT] Filling vehicle and load details...")

    _dump_page_fields(page)
    _debug_probe(page)
    _screenshot(page, "fields_debug_dump")

    if not extra:
        print("  [WARN] No extraFields provided — nothing to fill")
        return

    print(f"  [INFO] extraFields keys: {list(extra.keys())}")

    # ── 1. Vehicle Configuration (Knockout select) ──
    if permit_type == "fl_blanket_inner_bridge":
        veh_cfg = FL_INNER_BRIDGE_VEHICLE_CONFIG
        print(f'  [OVERRIDE] Vehicle Configuration forced to "{veh_cfg}" for inner bridge')
    else:
        veh_cfg = extra.get("vehicleConfig")
    if veh_cfg:
        _ko_select(page, "#VehicleConfigurationCode", str(veh_cfg), "Vehicle Configuration")
        page.wait_for_timeout(500)

    # ── 1b. Uncheck "This Vehicle is Legal Weight" — oversize trip permit by definition.
    # If left checked, FL's KO validator silently blanks dimension values that exceed legal limits
    # (e.g. width >8'6"). Must be off BEFORE filling width/height/length.
    try:
        legal_cb = page.locator("#IsLegalLoad").first
        if legal_cb.count() > 0 and legal_cb.is_checked():
            legal_cb.click()
            page.wait_for_timeout(300)
            print("  [UNCHECK] IsLegalLoad (oversize permit) \u2713")
    except Exception as e:
        print(f"  [WARN] Could not uncheck IsLegalLoad: {e}")

    # ── 2. Load Dimensions: height → width → length, each ft then inches.
    # Order matters: height first (lowest KO validation overhead), then width,
    # then length. Each full (ft+in) pair is committed before moving on, with a
    # short settle delay so FL's KO formatter doesn't race the next field.
    dim_sequence = [
        ("height", "#TotalHeightFeet", "#TotalHeightInches", "Total Height"),
        ("width",  "#TotalWidthFeet",  "#TotalWidthInches",  "Total Width"),
        ("length", "#TotalLengthFeet", "#TotalLengthInches", "Total Length"),
    ]
    for key, ft_sel, in_sel, label in dim_sequence:
        val = extra.get(key)
        if not val:
            continue
        ft, inch = _parse_ft_in(val)
        _safe_fill(page, ft_sel, ft, f"{label} (ft)")
        page.wait_for_timeout(300)
        _safe_fill(page, in_sel, inch, f"{label} (in)")
        page.wait_for_timeout(300)

    # ── 3. Vehicle Config dimensions: trailer / kingpin / front / rear ──
    vc_dim_map = {
        "trailerLength":   ("#TrailerLengthFeet",   "#TrailerLengthInches",   "Trailer Length"),
        "kingpinDistance": ("#KingpinDistanceFeet", "#KingpinDistanceInches", "Kingpin Distance"),
        "frontOverhang":   ("#FrontOverhangFeet",   "#FrontOverhangInches",   "Front Overhang"),
        "rearOverhang":    ("#RearOverhangFeet",    "#RearOverhangInches",    "Rear Overhang"),
    }
    for key, (ft_sel, in_sel, label) in vc_dim_map.items():
        val = extra.get(key)
        if not val:
            continue
        ft, inch = _parse_ft_in(val)
        _safe_fill(page, ft_sel, ft, f"{label} (ft)")
        _safe_fill(page, in_sel, inch, f"{label} (in)")

    # ── 2b. Post-verification sweep for all dimensions.
    # FL's KO runtime sometimes silently blanks dimension fields after they're committed
    # (observed: Total Height ft reported ✓ then ended up empty after unrelated later fills).
    # After ALL dimensions are written, re-read each and re-fill any that regressed.
    all_dims: list[tuple[str, str, str]] = []  # (selector, expected, label)
    for key, ft_sel, in_sel, label in dim_sequence:
        val = extra.get(key)
        if not val:
            continue
        ft, inch = _parse_ft_in(val)
        all_dims.append((ft_sel, ft, f"{label} (ft)"))
        all_dims.append((in_sel, inch, f"{label} (in)"))
    for key, (ft_sel, in_sel, label) in vc_dim_map.items():
        val = extra.get(key)
        if not val:
            continue
        ft, inch = _parse_ft_in(val)
        all_dims.append((ft_sel, ft, f"{label} (ft)"))
        all_dims.append((in_sel, inch, f"{label} (in)"))

    print("  [VERIFY] Post-fill dimension sweep...")
    for sweep_pass in range(1, 3):
        regressions: list[tuple[str, str, str]] = []
        for sel, expected, label in all_dims:
            try:
                actual = page.locator(sel).first.input_value()
            except Exception:
                actual = ""
            if _normalize(actual) != _normalize(expected):
                regressions.append((sel, expected, label))
                print(f'  [REGRESSED] {label}: expected "{expected}" got "{actual}"')
        if not regressions:
            print(f"  [VERIFY] All dimensions present \u2713 (pass {sweep_pass})")
            break
        print(f"  [VERIFY] Re-filling {len(regressions)} regressed field(s) (pass {sweep_pass})")
        for sel, expected, label in regressions:
            _safe_fill(page, sel, expected, f"{label} [resweep]")
            page.wait_for_timeout(200)
    else:
        # Final pass still had regressions — hard fail so we never silently submit a blank.
        final_bad = []
        for sel, expected, label in all_dims:
            try:
                actual = page.locator(sel).first.input_value()
            except Exception:
                actual = ""
            if _normalize(actual) != _normalize(expected):
                final_bad.append(f'{label} (expected "{expected}", got "{actual}")')
        if final_bad:
            _fatal(page, "Dimension fields blank after resweep: " + "; ".join(final_bad))

    # ── 4. Identity of Load (trip only) ──
    if permit_type == "trip":
        id_type = extra.get("identityOfLoadType")
        if id_type:
            _ko_select(page, "#IdentityOfLoadType", str(id_type), "Identity of Load Type")
            page.wait_for_timeout(300)
        id_val = extra.get("identityOfLoad")
        if id_val:
            _safe_fill(page, "#IdentityOfLoad", str(id_val), "Identity of Load")

    # Inner bridge has no load-info section at all — skip divisible + loadDesc.
    skip_load_info = (permit_type == "fl_blanket_inner_bridge")

    # ── 4b. Divisible Load (radio buttons "No" / "Yes") ──
    divisible = None if skip_load_info else extra.get("divisibleLoad")
    if divisible is not None and divisible != "":
        is_yes = str(divisible).strip().lower() in ("yes", "true", "1", "y")
        target = "Yes" if is_yes else "No"
        # FL renders this as two <input type="radio"> with data-bind linking them.
        # Click the one whose sibling label text matches.
        result = page.evaluate(
            """(target) => {
                // Walk the whole DOM for the text "Divisible Load" and then find the
                // nearest <input type="radio"> set in an ancestor container.
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                const candidates = [];
                while ((node = walker.nextNode())) {
                    const t = (node.textContent || '').trim().toLowerCase();
                    if (t.includes('divisible')) candidates.push(node);
                }
                for (const n of candidates) {
                    let p = n.parentElement;
                    for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
                        const radios = p.querySelectorAll('input[type="radio"]');
                        if (radios.length < 2) continue;
                        // Pick the radio whose label (for, next sibling, or parent text) matches target
                        for (const r of radios) {
                            let lt = '';
                            if (r.id) {
                                const lbl = document.querySelector('label[for="' + r.id + '"]');
                                if (lbl) lt = (lbl.textContent || '').trim();
                            }
                            if (!lt && r.nextElementSibling) lt = (r.nextElementSibling.textContent || '').trim();
                            if (!lt && r.parentElement) lt = (r.parentElement.textContent || '').trim().slice(0, 20);
                            if (lt.toLowerCase().includes(target.toLowerCase())) {
                                r.focus();
                                r.click();
                                r.dispatchEvent(new Event('change', {bubbles:true}));
                                if (typeof jQuery !== 'undefined') { jQuery(r).trigger('change'); }
                                return {ok:true, id:r.id, value:r.value, label:lt};
                            }
                        }
                        return {ok:false, reason:'no_label_match', radiosFound:radios.length};
                    }
                }
                return {ok:false, reason:'no_divisible_text'};
            }""",
            target,
        )
        if result.get("ok"):
            print(f'  [SELECT] Divisible Load: "{target}" \u2713')
            # Selecting "Yes" pops up an FDOT notice dialog that must be dismissed
            # before the rest of the form is interactive. Native alert() OR a
            # jQuery UI dialog — handle both.
            if is_yes:
                # Selecting "Yes" pops a jQuery UI dialog (.ui-dialog.ModalWindow)
                # titled "Divisible Load Notice" with a single "Ok" button. Click it
                # so the rest of the form becomes interactive again.
                page.wait_for_timeout(800)
                try:
                    ok_result = page.evaluate(
                        """() => {
                            const dialogs = [
                                ...document.querySelectorAll('.ui-dialog'),
                                ...document.querySelectorAll('[role="dialog"]'),
                                ...document.querySelectorAll('.modal.show, .modal.in'),
                                ...document.querySelectorAll('dialog'),
                            ].filter(d => d.offsetParent !== null);
                            for (const d of dialogs) {
                                const btns = Array.from(d.querySelectorAll('button, input[type="button"], input[type="submit"], a.ui-button'))
                                    .filter(b => b.offsetParent !== null && !b.disabled);
                                if (btns.length === 0) continue;
                                const ok = btns.find(b => {
                                    const t = (b.innerText || b.textContent || b.value || '').trim().toLowerCase();
                                    return t === 'ok' || t === 'okay' || t === 'continue' || t === 'close' || t === 'yes';
                                }) || btns[0];
                                ok.click();
                                return {ok:true, text: (ok.innerText || ok.textContent || ok.value || '').trim()};
                            }
                            return {ok:false};
                        }"""
                    )
                    if ok_result.get("ok"):
                        print(f'  [DISMISS] Divisible Load notice: clicked "{ok_result["text"]}" \u2713')
                    else:
                        print("  [DISMISS] No Divisible Load dialog found (nothing to dismiss)")
                except Exception as e:
                    print(f"  [WARN] Divisible Load dismiss raised: {e}")
                page.wait_for_timeout(500)
        else:
            print("  [WARN] Divisible Load radio not found on page")

    # ── 4c. Load Description ──
    # Variant behavior:
    #   trip:    free-text input near "Load Description" label
    #   bulk:    dropdown → "None of the above" → fill revealed text input
    #   flatbed: dropdown → first option (long construction text); no free text
    #   inner_bridge: skipped above
    if skip_load_info:
        load_desc = None
    elif permit_type in ("fl_blanket_bulk", "fl_blanket_flatbed"):
        # Dispatcher-selected choice: "construction" or "none_of_the_above"
        choice = (extra.get("loadDescriptionChoice") or "construction").strip().lower()
        # Discover the Load Description <select> dynamically — its id/name is not
        # stable across permit types. Walk the DOM for the literal "Load Description"
        # label and climb to the nearest visible <select>.
        dd_sel = page.evaluate(
            """() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    const t = (node.textContent || '').trim().toLowerCase();
                    if (!t.includes('load description')) continue;
                    let p = node.parentElement;
                    for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
                        const sels = p.querySelectorAll('select');
                        for (const el of sels) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (el.offsetParent === null) continue;
                            if (el.id)   return '#' + CSS.escape(el.id);
                            if (el.name) return 'select[name="' + el.name + '"]';
                            const uid = 'loadDescSelect_' + Date.now();
                            el.id = uid;
                            return '#' + uid;
                        }
                    }
                }
                return null;
            }"""
        )
        if not dd_sel:
            print("  [WARN] Load Description <select> not found near label — skipping")
        else:
            print(f"  [DISCOVER] Load Description select → {dd_sel}")
        try:
            if not dd_sel:
                load_desc = None
            elif choice == "none_of_the_above":
                _ko_select(page, dd_sel, "None of the above", "Load Description (dropdown)")
                page.wait_for_timeout(400)
                load_desc = extra.get("loadDescription")  # fill revealed free text
            else:
                # "Construction" → match the distinctive keyword; _ko_select's includes-fallback
                # handles punctuation/spacing drift in the portal's option text.
                _ko_select(page, dd_sel, "construction", "Load Description (Construction)")
                load_desc = None  # no free text when construction is chosen
        except Exception as e:
            print(f"  [WARN] Load-desc dropdown select failed: {e}")
            # Dump option texts for diagnosis so we can see what the portal actually offers
            try:
                opts = page.locator(dd_sel).first.evaluate(
                    "el => Array.from(el.options).map(o => o.text)"
                )
                print(f"  [DEBUG] Load-desc dropdown options: {opts}")
            except Exception:
                pass
            load_desc = None
    else:
        load_desc = extra.get("loadDescription")
    if load_desc:
        ld_sel = page.evaluate(
            """() => {
                // 1. Walk text nodes for "Load Description"
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    const t = (node.textContent || '').trim().toLowerCase();
                    if (!t.includes('load description')) continue;
                    // Walk up looking for a visible input/textarea
                    let p = node.parentElement;
                    for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
                        const els = p.querySelectorAll('input[type="text"], input:not([type]), textarea');
                        for (const el of els) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (el.offsetParent === null) continue;
                            if (el.id) return '#' + CSS.escape(el.id);
                            if (el.name) return '[name="' + el.name + '"]';
                            const uid = 'loadDescTarget_' + Date.now();
                            el.id = uid;
                            return '#' + uid;
                        }
                    }
                }
                return null;
            }"""
        )
        if ld_sel:
            try:
                _safe_fill(page, ld_sel, str(load_desc), "Load Description")
            except PermitError:
                print("  [WARN] Load Description fill failed")
        else:
            print("  [WARN] Load Description field not found on page (nothing visible near label)")

    _screenshot(page, "load_fields_filled")

    # ── 5. Axle Count ──
    # FL renders this as an unlabeled <input> whose cell's text contains "Number of Axles:".
    # We can't rely on label[for=], id, or name — they're all empty. Locate by walking
    # the DOM for the literal "Number of Axles" text and grabbing the nearest input
    # inside the SAME table row / cell.
    axle_count = extra.get("axleCount")
    if axle_count:
        axle_info = page.evaluate(
            """() => {
                // Find any element whose direct text contains "Number of Axles"
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    const txt = (node.textContent || '').trim().toLowerCase();
                    if (!txt.includes('number of axle')) continue;
                    // Walk up to a container that also contains an <input>
                    let p = node.parentElement;
                    for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
                        const inputs = p.querySelectorAll('input[type="text"], input:not([type])');
                        for (const el of inputs) {
                            if (el.type === 'hidden') continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 && rect.height === 0) continue;
                            // Build a unique selector
                            if (el.id) return {selector: '#' + CSS.escape(el.id), dataBind: el.getAttribute('data-bind') || '', value: el.value};
                            if (el.name) return {selector: 'input[name="' + el.name + '"]', dataBind: el.getAttribute('data-bind') || '', value: el.value};
                            // No id/name — give it one
                            const uid = 'axleCountTarget_' + Date.now();
                            el.id = uid;
                            return {selector: '#' + uid, dataBind: el.getAttribute('data-bind') || '', value: el.value, tagged: true};
                        }
                    }
                }
                return null;
            }"""
        )
        if axle_info:
            print(f'  [INFO] Axle Count field located: {axle_info}')
            _ko_fill(page, axle_info["selector"], str(axle_count), "Axle Count")
            page.wait_for_timeout(2500)  # wait for per-axle rows to render
        else:
            print("  [WARN] Axle Count field not found — per-axle fields won't render correctly")

    # ── 6. Axle Spacings (one row per axle after the first) ──
    # FL fields: #FeetFromPreviousAxle / #InchesFromPreviousAxle — but there's one pair
    # per axle row and ids are duplicated across rows. Grab them positionally.
    axle_spacings = extra.get("axleSpacings")
    if axle_spacings and isinstance(axle_spacings, list):
        ft_locs = page.locator('input[id="FeetFromPreviousAxle"]')
        in_locs = page.locator('input[id="InchesFromPreviousAxle"]')
        ft_count = ft_locs.count()
        in_count = in_locs.count()
        print(f"  [INFO] Found {ft_count} spacing ft fields, {in_count} spacing in fields")
        for i, spacing in enumerate(axle_spacings):
            if not spacing:
                continue
            ft, inch = _parse_ft_in(spacing)
            if i < ft_count:
                try:
                    loc = ft_locs.nth(i)
                    loc.click(click_count=3)
                    loc.fill(ft)
                    loc.press("Tab")
                    print(f'  [FILL] Axle {i+1}\u2192{i+2} spacing (ft): "{ft}" \u2713')
                except Exception as e:
                    print(f"  [WARN] Axle {i+1}\u2192{i+2} spacing ft error: {e}")
            else:
                print(f"  [WARN] No ft field for Axle Spacing {i+1}\u2192{i+2}")
            if i < in_count:
                try:
                    loc = in_locs.nth(i)
                    loc.click(click_count=3)
                    loc.fill(inch)
                    loc.press("Tab")
                    print(f'  [FILL] Axle {i+1}\u2192{i+2} spacing (in): "{inch}" \u2713')
                except Exception as e:
                    print(f"  [WARN] Axle {i+1}\u2192{i+2} spacing in error: {e}")

    # ── 7. Axle Weights (positional by duplicated #AxleWeight id) ──
    # Retry-until-verified per axle: FL's KO formatter sometimes commits a value
    # that's off by 1 (last axle observed as 27000 → 26999) when fill+Tab races
    # the async formatter. Read back after each type and retry up to 4 times.
    axle_weights = extra.get("axleWeights")
    if axle_weights and isinstance(axle_weights, list):
        weight_locs = page.locator('input[id="AxleWeight"]')
        wc = weight_locs.count()
        print(f"  [INFO] Found {wc} axle weight fields")
        for i, weight in enumerate(axle_weights):
            if weight in (None, ""):
                continue
            if i >= wc:
                print(f"  [WARN] No field for Axle {i+1} Weight")
                continue
            expected = str(weight)
            loc = weight_locs.nth(i)
            last_actual = ""
            for attempt in range(1, FILL_RETRIES + 1):
                try:
                    loc.click(click_count=3)
                    loc.fill("")
                    loc.fill(expected)
                    loc.press("Tab")
                except Exception as e:
                    print(f"  [WARN] Axle {i+1} Weight attempt {attempt} raised: {e}")
                page.wait_for_timeout(FILL_SETTLE_MS)
                try:
                    last_actual = loc.input_value().strip()
                except Exception:
                    last_actual = ""
                if _normalize(last_actual) == _normalize(expected):
                    print(f'  [FILL] Axle {i+1} Weight: "{expected}" \u2713 (attempt {attempt})')
                    break
                print(f'  [RETRY {attempt}/{FILL_RETRIES}] Axle {i+1} Weight — wanted "{expected}" got "{last_actual}"')
            else:
                _fatal(page, f'Axle {i+1} Weight never committed correctly after {FILL_RETRIES} attempts. Expected "{expected}", portal shows "{last_actual}".')

    _screenshot(page, "all_fields_filled")
    print("[OK] Vehicle and load details complete")


# ---------------------------------------------------------------------------
# Page 4: Save → Routing
# ---------------------------------------------------------------------------

def _save_and_route(page: Page, permit_type: str = "trip"):
    """Click Save, then navigate to the next tab.
    Trip permits → "Routing" tab. FL blanket variants → "Review & Submit" tab."""
    print("\n[ACT] Clicking Save...")

    try:
        save_btn = page.locator('button:has-text("Save"), input[value*="Save"], a:has-text("Save")')
        save_btn.first.click(timeout=10000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception as e:
        _fatal(page, f"Could not click Save: {e}")

    _screenshot(page, "saved")
    print("[OK] Saved")

    # FL Blanket variants skip routing entirely — they go straight to Review & Submit.
    is_blanket = permit_type.startswith("fl_blanket_")
    tab_label = "Review & Submit" if is_blanket else "Routing"
    tab_keywords = ["review"] if is_blanket else ["routing"]

    print(f"\n[ACT] Clicking {tab_label}...")
    # The target tab is a jQuery UI tab anchor (<a class="ui-tabs-anchor" tabindex="-1">).
    # Playwright refuses to click because tabindex=-1 makes it "not enabled". Activate the
    # tab directly via jQuery UI's tabs API, or failing that, dispatch a native click in JS.
    try:
        result = page.evaluate(
            """(keywords) => {
                // Strategy 1: jQuery UI tabs API — walk up from the target anchor to its .ui-tabs widget.
                const anchors = Array.from(document.querySelectorAll('a.ui-tabs-anchor'));
                const target = anchors.find(a => {
                    const t = (a.textContent || '').toLowerCase();
                    return keywords.every(k => t.includes(k));
                });
                if (!target) return {ok:false, err:'no_tab_anchor', anchors: anchors.map(a => (a.textContent || '').trim())};
                if (typeof jQuery !== 'undefined') {
                    let $tabs = jQuery(target).closest('.ui-tabs');
                    if ($tabs.length && $tabs.tabs) {
                        const panels = $tabs.find('> div[role="tabpanel"], > div.ui-tabs-panel');
                        const panelId = target.getAttribute('href') || '';
                        let idx = -1;
                        $tabs.find('a.ui-tabs-anchor').each(function(i, a) {
                            if (a === target) idx = i;
                        });
                        if (idx >= 0) {
                            try { $tabs.tabs('option', 'active', idx); return {ok:true, via:'tabs_api', idx, panelId}; }
                            catch (e) { /* fall through */ }
                        }
                    }
                }
                // Strategy 2: native click on the parent <li> (jQuery UI listens there too)
                const li = target.closest('li');
                if (li) { li.click(); return {ok:true, via:'li_click'}; }
                // Strategy 3: direct anchor click bypassing focusable check
                target.click();
                return {ok:true, via:'anchor_click'};
            }""",
            tab_keywords,
        )
        if not result.get("ok"):
            _fatal(page, f"Could not activate {tab_label} tab: {result}")
        print(f'  [{tab_label.upper()}] Activated via {result.get("via")}')
        page.wait_for_timeout(1500 if is_blanket else 2500)
    except Exception as e:
        _fatal(page, f"Could not click {tab_label}: {e}")

    _screenshot(page, "review_reached" if is_blanket else "routing_reached")
    print("[STOP] =============================================")
    print(f"[STOP] {tab_label} page reached — permit automation complete.")
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
    Run the Florida trip permit automation for one driver.

    Args:
        permit:            Enriched permit dict from the backend.
        job_id:            The parent job ID (for logging/screenshots).
        on_captcha_needed: Callback if CAPTCHA appears.
        company:           Company constants dict from config.py.

    Returns:
        Result dict with "status", "permitId", etc.
    """
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"
    tractor = driver.get("tractor", "")
    permit_id = permit["permitId"]
    permit_type = permit.get("permitType", "")
    extra = permit.get("extraFields") or permit.get("loadDetails") or {}

    # Credentials
    username = os.getenv("FL_PORTAL_USERNAME")
    password = os.getenv("FL_PORTAL_PASSWORD")
    if not username or not password:
        return {
            "permitId": permit_id,
            "driverName": driver_name,
            "tractor": tractor,
            "permitType": permit_type,
            "status": "error",
            "message": "Missing FL_PORTAL_USERNAME or FL_PORTAL_PASSWORD in .env",
        }

    phone = company.get("phone", "")

    if not company:
        from config import COMPANY
        company = COMPANY

    print(f"[Florida] Starting permit {permit_id} for {driver_name} ({tractor})")
    print(f"[Florida] Permit type: {permit_type}")
    if extra:
        print(f"[Florida] Extra fields: {list(extra.keys())}")

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
            # Step 1: Login
            _login(page, username, password)

            # Step 2: Create Application → fill permittee info → continue
            _create_application(page)
            _fill_permittee_info(page, company, phone)

            # Step 3: Permit type + dates (dispatcher supplies the date for all variants)
            _fill_permit_type_and_dates(page, permit_type, permit.get("effectiveDate", "") or "")

            # Step 4: Select "New Vehicle" from dropdown → renders vehicle/load fields
            _select_new_vehicle(page)
            _fill_vehicle_and_load(page, permit, extra, permit_type)

            # Step 5: Save → Routing (or Review & Submit for FL blanket variants)
            _save_and_route(page, permit_type)

            screenshot_path = _screenshot(page, "complete")

            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "success",
                "message": "Routing page reached — permit automation complete",
                "screenshot": screenshot_path,
            }

        except PermitError as e:
            return {
                "permitId": permit_id,
                "driverName": driver_name,
                "tractor": tractor,
                "permitType": permit_type,
                "status": "error",
                "message": str(e),
                "screenshot": e.screenshot_path,
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
