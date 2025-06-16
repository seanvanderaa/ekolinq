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

def verifyInfo(fname, lname, email, address, city, zip, gated):
    print (fname, lname, email, address, city, zip, gated)

# app/services/address_validation.py
import requests
from flask import current_app
from wtforms import ValidationError

def verifyAddress(full_addr, place_id, user_city, user_zip):
    key = current_app.config["GOOGLE_API_KEY"]

    if place_id:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "address_components",
                "key": key,
            },
            timeout=3,
        )
        data = r.json()
        if data.get("status") == "OK":
            comps = data["result"]["address_components"]
            def has(t, val):
                return any(t in c["types"] and c["long_name"].lower() == val.lower()
                           for c in comps)
            if has("locality", user_city) and has("postal_code", user_zip):
                return        # ✅ city & ZIP match this Place ID
            # else fall through and geocode the text for a second opinion

    # Fallback: geocode the raw text
    r = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={
            "address":    full_addr,
            "components": "country:US",
            "key":        key,
        },
        timeout=3,
    )
    data = r.json()
    if data.get("status") != "OK" or not data["results"]:
        raise ValidationError("Address not found—please check the spelling and ensure all of the details—address, city, ZIP—are correct.")

    