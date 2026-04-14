"""
Backend-driven form field schemas for state-specific permit requirements.

Each entry in FIELD_SCHEMAS maps a (state, permitType) tuple to a list of
field definitions.  Key (state, None) means "all permit types for this state."

The frontend calls GET /api/permits/form-fields?states=GA,FL&permitType=os_ow
and renders whatever fields come back — no React conditional logic needed.

Adding a new state's fields:
  1. Add entries to FIELD_SCHEMAS below.
  2. That's it — the frontend picks them up automatically.
"""


# ── Field Schemas ────────────────────────────────────────────────────

FIELD_SCHEMAS: dict[tuple[str, str | None], list[dict]] = {

    # ── Georgia OS/OW ────────────────────────────────────────────────
    ("GA", "os_ow"): [
        # Load Dimensions
        {"key": "width",  "label": "Width",  "type": "text", "placeholder": "e.g. 12'6\"", "group": "Load Dimensions"},
        {"key": "height", "label": "Height", "type": "text", "placeholder": "e.g. 14'2\"", "group": "Load Dimensions"},
        {"key": "length", "label": "Length", "type": "text", "placeholder": "e.g. 75'0\"", "group": "Load Dimensions"},
        {"key": "weight", "label": "Weight (lbs)", "type": "text", "placeholder": "e.g. 95000", "group": "Load Dimensions"},
        # Axle Configuration
        {"key": "axleCount", "label": "Number of Axles", "type": "select", "group": "Axle Configuration",
         "options": [{"value": str(n), "label": f"{n} axles"} for n in range(2, 10)]},
        {"key": "axleSpacings", "label": "Axle Spacings", "type": "axle_group", "group": "Axle Configuration",
         "dependsOn": "axleCount"},
        # Route
        {"key": "origin",           "label": "Origin",            "type": "text",     "placeholder": "Starting point",      "group": "Route"},
        {"key": "destination",      "label": "Destination",       "type": "text",     "placeholder": "Ending point",        "group": "Route"},
        {"key": "routeDescription", "label": "Route Description", "type": "textarea", "placeholder": "Roads, highways...",  "group": "Route"},
    ],

}


# ── Florida schema fragments ─────────────────────────────────────────
# All FL dimension fields are ft/in split (matches TotalWidthFeet/Inches etc on the portal).
# FL has no gross-weight field — it's derived from axle weight sum.
# Select option values/labels must match the FL portal's <option> text EXACTLY (case-sensitive).

_FL_VEHICLE_CONFIG_OPTIONS = [
    {"value": "Truck Tractor Semitrailer Hauling", "label": "Truck Tractor Semitrailer Hauling"},
    {"value": "Inner Bridge", "label": "Inner Bridge"},
]

_FL_COMMON: list[dict] = [
    # Load Dimensions
    {"key": "width",  "label": "Total Width",  "type": "dimension_ft_in", "group": "Load Dimensions"},
    {"key": "height", "label": "Total Height", "type": "dimension_ft_in", "group": "Load Dimensions"},
    {"key": "length", "label": "Total Length", "type": "dimension_ft_in", "group": "Load Dimensions"},
    # Vehicle Config
    {"key": "trailerLength",   "label": "Trailer Length",   "type": "dimension_ft_in", "group": "Vehicle Config"},
    {"key": "kingpinDistance", "label": "Kingpin Distance", "type": "dimension_ft_in", "group": "Vehicle Config"},
    {"key": "frontOverhang",   "label": "Front Overhang",   "type": "dimension_ft_in", "group": "Vehicle Config"},
    {"key": "rearOverhang",    "label": "Rear Overhang",    "type": "dimension_ft_in", "group": "Vehicle Config"},
    {"key": "vehicleConfig", "label": "Vehicle Configuration", "type": "select",
     "group": "Vehicle Config", "options": _FL_VEHICLE_CONFIG_OPTIONS},
    # Axle Configuration
    {"key": "axleCount", "label": "Number of Axles", "type": "select", "group": "Axle Configuration",
     "options": [{"value": str(n), "label": f"{n} axles"} for n in range(2, 10)]},
    {"key": "axleSpacings", "label": "Axle Spacings", "type": "axle_group", "group": "Axle Configuration",
     "dependsOn": "axleCount"},
    {"key": "axleWeights", "label": "Axle Weights (lbs)", "type": "axle_weight_group", "group": "Axle Configuration",
     "dependsOn": "axleCount"},
]

# Trip-only extras: identity of load + divisible + free-text load description
_FL_TRIP_EXTRA: list[dict] = [
    {"key": "identityOfLoadType", "label": "Identity of Load Type", "type": "select", "group": "Load Info",
     "options": [
         {"value": "Bill Of Lading",        "label": "Bill Of Lading"},
         {"value": "Equipment Vin",         "label": "Equipment Vin"},
         {"value": "Load Id",               "label": "Load Id"},
         {"value": "Trailer Or Truck Unit", "label": "Trailer Or Truck Unit"},
         {"value": "Truck Or Trailer Tag",  "label": "Truck Or Trailer Tag"},
     ]},
    {"key": "identityOfLoad", "label": "Identity of Load (ID)", "type": "text",
     "placeholder": "VIN / BOL / tag / unit #", "group": "Load Info"},
    {"key": "divisibleLoad", "label": "Divisible Load?", "type": "select", "group": "Load Info",
     "options": [{"value": "No", "label": "No"}, {"value": "Yes", "label": "Yes"}]},
    {"key": "loadDescription", "label": "Load Description", "type": "text",
     "placeholder": "Describe the load", "group": "Load Info"},
]

# Dispatcher-facing choice for the FL load-description dropdown. Two clear options:
#   - "Construction" → runner picks the long construction-text option on the portal
#   - "None of the above" → runner picks that portal option (bulk also reveals a free-text field)
_FL_LOAD_DESC_CHOICE = {
    "key": "loadDescriptionChoice", "label": "Load Description", "type": "select",
    "group": "Load Info",
    "options": [
        {"value": "construction",      "label": "Construction Or Industrial Material/Equipment Or Prefabricated Structural Item"},
        {"value": "none_of_the_above", "label": "None of the above"},
    ],
}

# Blanket Bulk: divisible + choice dropdown + free-text fallback (used when "None of the above")
_FL_BULK_EXTRA: list[dict] = [
    {"key": "divisibleLoad", "label": "Divisible Load?", "type": "select", "group": "Load Info",
     "options": [{"value": "No", "label": "No"}, {"value": "Yes", "label": "Yes"}]},
    _FL_LOAD_DESC_CHOICE,
    {"key": "loadDescription", "label": "Load Description (if \"None of the above\")", "type": "text",
     "placeholder": "Describe the load", "group": "Load Info"},
]

# Inner Bridge: nothing extra. Runner hard-codes the Inner Bridge vehicle config option.
_FL_INNER_BRIDGE_EXTRA: list[dict] = []

# Flatbed: divisible + same load-description choice dropdown. Runner computes the
# travel begin date (+2 work days, or +3 if after 4 PM).
_FL_FLATBED_EXTRA: list[dict] = [
    {"key": "divisibleLoad", "label": "Divisible Load?", "type": "select", "group": "Load Info",
     "options": [{"value": "No", "label": "No"}, {"value": "Yes", "label": "Yes"}]},
    _FL_LOAD_DESC_CHOICE,
    {"key": "loadDescription", "label": "Load Description (if \"None of the above\")", "type": "text",
     "placeholder": "Describe the load", "group": "Load Info"},
]

FIELD_SCHEMAS[("FL", "trip")]                     = _FL_COMMON + _FL_TRIP_EXTRA
FIELD_SCHEMAS[("FL", "fl_blanket_bulk")]          = _FL_COMMON + _FL_BULK_EXTRA
FIELD_SCHEMAS[("FL", "fl_blanket_inner_bridge")]  = (
    [f for f in _FL_COMMON if f["key"] != "vehicleConfig"] + _FL_INNER_BRIDGE_EXTRA
)
FIELD_SCHEMAS[("FL", "fl_blanket_flatbed")]       = _FL_COMMON + _FL_FLATBED_EXTRA
# Wildcard fallback (e.g. for fuel/trip_fuel) → behave like trip
FIELD_SCHEMAS[("FL", None)] = _FL_COMMON + _FL_TRIP_EXTRA


# ── Merge / lookup ───────────────────────────────────────────────────

def get_merged_fields(states: list[str], permit_type: str) -> list[dict]:
    """
    Return the union of field schemas for the given states + permit type.

    Lookup order per state:
      1. (state, permit_type)   — exact match
      2. (state, None)          — wildcard for all types

    Fields are deduplicated by `key` (first occurrence wins).
    """
    seen_keys: set[str] = set()
    merged: list[dict] = []

    for state in states:
        fields = FIELD_SCHEMAS.get((state, permit_type)) or FIELD_SCHEMAS.get((state, None)) or []
        for field in fields:
            if field["key"] not in seen_keys:
                seen_keys.add(field["key"])
                merged.append(field)

    return merged
