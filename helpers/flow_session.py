# helpers/flow_session.py
import time
from functools import wraps
from flask import session, request, g
from itsdangerous import BadSignature, SignatureExpired
from werkzeug.exceptions import HTTPException
from helpers.capture_ip import client_ip            # already in your tree

FLOW_WINDOW_SECS = 5 * 60       # 5‑min token lifetime

class SessionExpired(HTTPException):
    code = 440
    description = "Session expired"

# ────────────────────────────────────────────
# token helpers – unchanged from your app.py
# ────────────────────────────────────────────
def new_confirm_token(serializer, request_id: str) -> str:
    return serializer.dumps({"rid": request_id, "ip": client_ip()})

def verify_confirm_token(serializer, token: str, max_age: int = FLOW_WINDOW_SECS):
    data = serializer.loads(token, max_age=max_age)
    if data.get("ip") != client_ip():
        raise BadSignature("IP mismatch")
    return data["rid"]

# ────────────────────────────────────────────
# decorator to guard *every* wizard step
# ────────────────────────────────────────────
def pickup_flow_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        rid_param = (
            kwargs.get("request_id")
            or request.args.get("request_id")
            or request.form.get("request_id")
        )
        rid_sess  = session.get("pickup_request_id")
        token     = session.get("confirm_token")
        exp       = session.get("confirm_expires", 0)

        # 1) must be the same request id
        if rid_param != rid_sess:
            raise SessionExpired()

        # 2) token signature / age / IP
        try:
            from flask import current_app          # local import to avoid cycles
            verify_confirm_token(current_app.serializer, token)
        except (SignatureExpired, BadSignature, TypeError):
            raise SessionExpired()

        # 3) clock‑based expiry
        if time.time() > exp:
            session.clear()
            raise SessionExpired()

        # pass the id downstream if useful
        g.request_id = rid_sess
        return fn(*args, **kwargs)
    return wrapper
