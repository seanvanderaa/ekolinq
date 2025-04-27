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
    