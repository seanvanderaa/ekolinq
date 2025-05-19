from flask import request

def code_email_key() -> str:
    """
    Combine the 6-digit confirmation code and the e-mail address so that
    each pair gets its *own* bucket.
    """
    # Flask parses form data lazily – this is safe inside key_func.
    code  = (request.form.get('request_id')      or "").strip()
    email = (request.form.get('requester_email') or "").lower().strip()

    # fall back to JSON payload if you ever migrate to fetch/AJAX
    if request.is_json:
        data  = request.get_json(silent=True) or {}
        code  = data.get('request_id', code)
        email = data.get('requester_email', email)

    return f"{code}:{email}"