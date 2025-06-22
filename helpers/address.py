import json

def verifyZip(zip_list, zip_code):
    # Check if zip_code is a valid format (5 digits)
    if not zip_code.isdigit() or len(zip_code) != 5:
        return {
            "valid": False,
            "reason": "Please enter a zip code. This must be 5 digits and cannot contain any letters."
        }

    # Check if zip_code is in the approved list
    if zip_code not in zip_list:
        return {
            "valid": False,
            "reason": "We're sorry, we don't currently service your area. Please get in touch if you think this is a mistake!"
        }

    # Zip code is valid and serviced
    return {
        "valid": True,
        "reason": ""
    }

import hashlib
import json
import logging
import requests
from flask import current_app

class AddressError(Exception):   # keeps your ValidationError semantics
    pass

def verifyAddress(full_addr: str,
                   place_id: str | None,
                   user_city: str,
                   user_zip: str) -> tuple[bool, str]:
    """
    Returns (is_valid, message).
    • Never logs PII (full address, city, ZIP).
    • Surfaces a clear message when the Address Validation API is unavailable.
    """
    log = current_app.logger
    key = current_app.config["GOOGLE_BACKEND_API_KEY"]

    def _anonymise(text: str) -> str:
        """8-char stable hash for traceability without leaking PII."""
        return hashlib.sha256(text.encode()).hexdigest()[:8]

    req_id = _anonymise(full_addr)
    log.info("verify_address[%s]: place=%s", req_id, bool(place_id))

    # ------------- helper for component comparison -------------------
    def _extract(comp, kind):
        if kind in comp.get("types", []):
            return comp.get("long_name", "").lower()
        if comp.get("componentType") == kind:
            return comp.get("componentName", {}).get("text", "").lower()
        return None

    def _match(comps):
        city_ok = any(_extract(c, "locality")     == user_city.lower()
                      for c in comps)
        zip_ok  = any(_extract(c, "postal_code")  == user_zip
                      for c in comps)
        if city_ok and zip_ok:
            return True, ""
        msg = []
        if not city_ok:
            msg.append("city")
        if not zip_ok:
            msg.append("ZIP")
        return False, f"The {', '.join(msg)} doesn’t match Google’s data."

    # ───────── 1) Place Details — only if a place_id was provided ─────
    if place_id:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "address_components",
                "key": key,
            },
            timeout=3,
        )
        if resp.ok and resp.json().get("status") == "OK":
            ok, msg = _match(resp.json()["result"]["address_components"])
            log.info("place_vrdct[%s]: %s", req_id, ok)
            return ok, msg
        # otherwise fall through

    # ───────── 2) Address Validation fallback ─────────────────────────
    payload = {
        "address":         {"regionCode": "US", "addressLines": [full_addr]},
        "enableUspsCass":  True,
    }
    resp = requests.post(
        "https://addressvalidation.googleapis.com/v1:validateAddress",
        params={"key": key},
        json=payload,
        timeout=3,
    )

    if not resp.ok:
        # API unavailable: do NOT attempt to judge the address
        log.warning("addr_api_fail[%s]: HTTP %s", req_id, resp.status_code)
        raise AddressError(
            "Our address verification service is temporarily unavailable "
            "— please contact us."
        )

    rj       = resp.json()
    result   = rj.get("result", {})
    verdict  = result.get("verdict", {})

    # Required high-confidence flags
    if not verdict.get("addressComplete"):
        log.info("Address had to be fixed [%s]", req_id)
        return False, "Google could not find a complete match for that address."

    if any(verdict.get(f) for f in (
            "hasReplacedComponents",
            "hasUnconfirmedComponents")):
        log.info("addr_fixed[%s]", req_id)
        return False, ("Some part of the address is incorrect—we could not find the address you've listed. Please double-check and try again. If the error persists, please contact us.")

    ok, msg = _match(result.get("address", {}).get("addressComponents", []))
    log.info("addr_vrdct[%s]: %s", req_id, ok)
    return ok, msg
