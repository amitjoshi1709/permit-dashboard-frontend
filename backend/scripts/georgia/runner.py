"""
Georgia DMV Portal — Playwright Automation (placeholder)

TODO: Implement actual Georgia portal form filling.
Follow the same pattern as scripts/alabama/runner.py.
"""

from typing import Callable, Optional


def run(permit: dict, job_id: str, on_captcha_needed: Optional[Callable] = None) -> dict:
    driver = permit["driver"]
    driver_name = f"{driver['firstName']} {driver['lastName']}"

    return {
        "permitId": permit["permitId"],
        "driverName": driver_name,
        "tractor": driver["tractor"],
        "permitType": permit.get("permitType", ""),
        "status": "error",
        "message": "Georgia automation not yet implemented",
    }
