# auth.py  (keep it in its own module)
import time, requests
from authlib.jose import jwt, JsonWebKey
from authlib.jose.errors import JoseError
from flask import current_app

_JWKS: JsonWebKey = None
_JWKS_TS = 0          # unix epoch of last fetch
_CACHE_TTL = 60 * 60  # refresh keys every hour

def _get_jwks() -> JsonWebKey:
    global _JWKS, _JWKS_TS
    if _JWKS is None or time.time() - _JWKS_TS > _CACHE_TTL:
        issuer = (
            f"https://cognito-idp.{current_app.config['COGNITO_REGION']}"
            f".amazonaws.com/{current_app.config['COGNITO_USER_POOL_ID']}"
        )
        jwks_uri = f"{issuer}/.well-known/jwks.json"
        _JWKS = JsonWebKey.import_key_set(requests.get(jwks_uri, timeout=5).json())
        _JWKS_TS = time.time()
    return _JWKS


def verify_cognito_jwt(token: str) -> dict:
    """Return the decoded claims *only* if the token is still valid."""
    jwks = _get_jwks()
    claims = jwt.decode(token, jwks)          # signature + alg/kid check
    # Verify standard claims (exp / iat / nbf) and custom ones we care about
    claims.validate()                         # checks exp / iat / nbf
    expected_iss = (
        f"https://cognito-idp.{current_app.config['COGNITO_REGION']}"
        f".amazonaws.com/{current_app.config['COGNITO_USER_POOL_ID']}"
    )
    if claims["iss"] != expected_iss:
        raise JoseError("bad issuer")
    if claims["aud"] != current_app.config["COGNITO_CLIENT_ID"]:
        raise JoseError("wrong audience")
    if claims["token_use"] != "id":
        raise JoseError("not an ID-token")
    return claims
