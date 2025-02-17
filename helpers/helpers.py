from datetime import date, timedelta, datetime

def format_date(date_str):
    """
    Converts a date string (YYYY-MM-DD) into a formatted string like:
    "Friday, Dec. 25th"
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    day = d.day
    # Determine ordinal suffix
    if 11 <= day <= 13:
        ordinal = "th"
    else:
        ordinal = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return d.strftime("%A, %b. ") + str(day) + ordinal