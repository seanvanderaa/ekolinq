# app.py
import os
import csv
import io
import json
import uuid
import time
import logging
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import urlencode, urlparse, quote_plus

from flask import (Flask, request, render_template, redirect, url_for, jsonify,
                   make_response, session, current_app, flash, abort, g)
from flask_wtf import CSRFProtect
from wtforms import ValidationError
from flask_wtf.csrf import validate_csrf, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_sitemap import Sitemap

from werkzeug.middleware.proxy_fix import ProxyFix

import traceback

from upstash_redis import Redis

from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt, JsonWebKey
import requests
from sqlalchemy import func, or_
from pycognito import Cognito
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from helpers.analytics import get_admin_metrics, city_distribution, awareness_distribution
from helpers.monitoring import (
    EmailErrorHandler,
    record_login_failure,    # already in use
    record_404,
    record_5xx,
    record_slow,
    start_monitoring_threads,
)
from helpers.cus_limiter import code_email_key
from helpers.address import verifyZip, verifyAddress, AddressError
from helpers.helpers import format_date
from helpers.capture_ip import client_ip
import helpers.import_backfill as backfill_mod
# from helpers.routing import compute_optimized_route, seconds_to_hms
from helpers.mapbox_routing import compute_optimized_route, seconds_to_hms, _maybe_geocode, _coords_like, hms_to_seconds, seconds_to_pretty
from helpers.scheduling import build_schedule
from helpers.emailer import (send_contact_email, send_request_email,
                             send_error_report, send_edited_request_email, send_cancellation_email)
from helpers.auth import verify_cognito_jwt, JoseError
from helpers.export import weekly_export
from helpers.forms import (RequestForm, DateSelectionForm, UpdateAddressForm,
                           PickupStatusForm, AdminScheduleForm, AdminAddressForm,
                           ScheduleDayForm, DateRangeForm, EditRequestTimeForm,
                           CancelEditForm, CancelRequestForm, EditRequestInitForm,
                           DeletePickupForm, ContactForm, CleanPickupsForm, AddPickupNotes,
                           updateCustomerNotes, RatingForm)

from models import (db, PickupRequest, ServiceSchedule, DriverLocation,
                    RouteSolution, Config as DBConfig, add_request,
                    get_service_schedule, get_address)
from extensions import mail

# ──────────────────────────────────────────────────────────────────────────
# Environment & configuration
# ──────────────────────────────────────────────────────────────────────────
if os.getenv("FLASK_CONFIG") != "production":
    load_dotenv()    

from config import DevelopmentConfig, ProductionConfig

CONFIG_NAME = os.getenv("FLASK_CONFIG", "development")   # default “development”
ConfigClass = ProductionConfig if CONFIG_NAME == "production" else DevelopmentConfig

# ──────────────────────────────────────────────────────────────────────────
# Extension singletons
# ──────────────────────────────────────────────────────────────────────────
csrf    = CSRFProtect()
limiter = Limiter(
    key_func=client_ip,
    default_limits=ConfigClass.DEFAULT_RATE_LIMITS
)

redis = Redis.from_env() 

# ──────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────
def create_app():

    # --------------------------------------------------
    # APP INITIALIZATION
    # --------------------------------------------------
    app = Flask(__name__)
    sitemap = Sitemap(app=app)
    app.config.from_object(ConfigClass)

    # OAuth (Amazon Cognito)
    oauth = OAuth(app)
    COGNITO_DOMAIN    = app.config["COGNITO_DOMAIN"]      # demo-domain.auth.us-east-2.amazoncognito.com
    COGNITO_CLIENT_ID = app.config["COGNITO_CLIENT_ID"]
    COGNITO_REGION = app.config["COGNITO_REGION"]
    GOOGLE_API_KEY = app.config["GOOGLE_API_KEY"]

    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt="pickup-confirm")

    issuer_base = (
        f"https://cognito-idp.{app.config['COGNITO_REGION']}.amazonaws.com/"
        f"{app.config['COGNITO_USER_POOL_ID']}"
    )
    oauth.register(
        name="oidc",
        client_id=app.config["COGNITO_CLIENT_ID"],
        client_secret=app.config["COGNITO_CLIENT_SECRET"],
        authority=issuer_base,
        server_metadata_url=f"{issuer_base}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email phone"},
    )

    # --------------------------------------------------
    # LIMITER FUNCTIONALITY
    # --------------------------------------------------
    if app.config["RATELIMIT_STORAGE_URI"]:
        limiter.storage_uri = app.config["RATELIMIT_STORAGE_URI"]  # e.g. Redis in prod

    from limits.storage import RedisStorage
    if CONFIG_NAME == "production":
        limiter.storage_uri = app.config["RATELIMIT_STORAGE_URI"]
    else:
        limiter.storage_uri = "memory://"
    limiter.init_app(app)

    # Put ProxyFix before the limiter so it sees the real client IP
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # --------------------------------------------------
    # FLASK TALISMAN & SECURE HEADERS
    # --------------------------------------------------
    SELF = "'self'"

    csp = {
        "default-src":   [SELF],
        "script-src":    [
            "'strict-dynamic'",
            SELF,
            "https://ajax.googleapis.com",
            "https://cdnjs.cloudflare.com",
            "https://cdn.jsdelivr.net",        # your JS bundles
            "https://www.google.com",          # reCAPTCHA loader
            "https://www.gstatic.com",         # reCAPTCHA iframe
            "https://maps.googleapis.com",
            'https://maps.gstatic.com',
            "https://www.googletagmanager.com"
        ],
        "style-src":     [
            SELF,
            "https://fonts.googleapis.com", 
            "https://cdn.jsdelivr.net",       
        ],
        "img-src":     [
            SELF, 
            "data:",
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
            "https://maps.gstatic.com",
            "https://maps.googleapis.com"
        ],
        "connect-src":   [SELF,
            "https://maps.googleapis.com",
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
            "https://www.googletagmanager.com"
        ],
        "worker-src": [
            "blob:"                       # required for Web Workers in Search JS
        ],
        "child-src": [
            "blob:"                       # likewise
        ],
        "font-src": [
            "https://fonts.gstatic.com",
            "https://cdn.jsdelivr.net",
            "data:"
        ],
        "frame-src":     [
            "https://maps.googleapis.com",
            "https://www.google.com",          # reCAPTCHA iframe
            "https://www.gstatic.com",
        ],
        "base-uri" : [SELF],
        "frame-ancestors": [SELF],
        "form-action":     [SELF],
    }

    talisman = Talisman(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=["script-src", "style-src"],
        frame_options="DENY",
        referrer_policy="same-origin",
        permissions_policy={"geolocation": "()", "microphone": "()"},
        force_https=app.config["FORCE_HTTPS"],
        strict_transport_security=app.config["STRICT_TRANSPORT_SECURITY"],
        strict_transport_security_max_age=31536000,
        strict_transport_security_preload=True,
    )

    # --------------------------------------------------
    # COOKIE / SESSION FLAGS
    # --------------------------------------------------
    # HTTP-only and SameSite already set in BaseConfig
    # Secure flag toggles automatically via ConfigClass

    # --------------------------------------------------
    # EXTENSIONS
    # --------------------------------------------------
    mail.init_app(app)
    csrf.init_app(app)
    db.init_app(app)

    from flask_migrate import Migrate
    migrate = Migrate(app, db)

    # Create tables once if needed
    #with app.app_context():
        #db.drop_all()
        #db.create_all()
        #seed_schedule_if_necessary()

    # --------------------------------------------------
    # RATE-LIMIT SCOPES (shared limits)
    # --------------------------------------------------
    def user_or_ip():
        if g.get("current_user"):                 # set in the login_required wrapper
            return g.current_user["sub"]
        return client_ip()

    edit_scope = limiter.shared_limit("20 per hour;4 per minute",
                                      scope="edit-flow", key_func=user_or_ip)
    
    approval_scope = limiter.shared_limit("15 per hour;5 per minute",
                                        scope="edit-approval",
                                        key_func=client_ip)

    in_window_scope = limiter.shared_limit("300 per hour;30 per minute",
                                        scope="edit-inwindow",
                                        key_func=user_or_ip)

    code_email_scope = limiter.shared_limit("30 per hour;10 per minute",
                                            scope="edit-code-email",
                                            key_func=code_email_key)

    # --------------------------------------------------
    # SESSION-HELPER HOOKS
    # --------------------------------------------------
    @app.before_request
    def session_auto_timeout():
        exp = session.get("expires_at")
        if exp and exp < time.time():
            session.clear()

    @app.before_request
    def _monitor_start():
        g._start_time = time.time()

    @app.after_request
    def set_coop(response):
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return response

    @app.after_request
    def _monitor_response(response):
        if response.status_code == 404:
            record_404()
        elif 500 <= response.status_code < 600:
            record_5xx()

        # slow-response spike
        duration = time.time() - getattr(g, "_start_time", time.time())
        record_slow(duration)

        return response

    @app.context_processor
    def inject_contact_form():
        return {"contact_form": ContactForm()}

    # --------------------------------------------------
    # LOGIN SECURITY (verify Cognito JWT)
    # --------------------------------------------------
    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            id_token = session.get("id_token")
            if not id_token:
                record_login_failure()
                return redirect(url_for("admin_login", next=request.url))
            try:
                claims = verify_cognito_jwt(id_token)
            except JoseError:
                session.clear()
                record_login_failure()
                return redirect(url_for("admin_login", next=request.url))
            g.current_user = {
                "sub": claims["sub"],
                "email": claims.get("email"),
                "groups": claims.get("cognito:groups", []),
            }
            return fn(*args, **kwargs)
        return wrapper
    
    # --------------------------------------------------
    # EDIT REQUEST SECURITY
    # --------------------------------------------------
    
    def edit_window_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Where is the id coming from?
            rid = (
                kwargs.get("request_id") or            # URL kwarg <string:request_id>
                request.args.get("request_id") or
                request.form.get("request_id")
            )

            token  = session.get("edit_token")
            exp    = session.get("edit_expires", 0)

            if not (token and rid and time.time() < exp and verify_edit_token(token, rid)):
                flash("Your edit session has expired – please start again.", "warning")
                session.pop("edit_token",    None)
                session.pop("edit_expires",  None)
                return redirect(url_for("edit_request_init"))

            # (optional) sliding window – uncomment next line if you want it
            # session["edit_expires"] = time.time() + EDIT_WINDOW_SECS
            return fn(*args, **kwargs)
        return wrapper

    # --------------------------------------------------
    # LOGGING
    # --------------------------------------------------
    if not app.debug and not app.testing:
        handler = logging.StreamHandler()           # writes to STDOUT
        handler.setLevel(app.config["LOGGER_LEVEL"])
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        ))
        app.logger.addHandler(handler)

    if not app.testing:
        start_monitoring_threads()

    app.logger.setLevel(app.config["LOGGER_LEVEL"])
    app.logger.info('LOGGER LEVEL: %s', app.config["LOGGER_LEVEL"])
    app.logger.info('FLASK LEVEL: %s', CONFIG_NAME)

    if limiter.enabled:            # only safe when enabled
        app.logger.info("Rate-limit storage: %s", limiter.storage)
    else:
        app.logger.info("WARN: Rate limiting disabled!")
    
    if not app.debug and not app.testing and app.config.get("MAIL_SERVER"):
        email_handler = EmailErrorHandler()
        email_handler.setLevel(logging.ERROR)
        app.logger.addHandler(email_handler)


    # --------------------------------------------------
    # REQUEST SESSION HANDLING FOR NEW REQUESTS & CONFIRMATION
    # --------------------------------------------------

    def new_confirm_token(request_id: str) -> str:
        """Token contains request id and caller’s IP."""
        return serializer.dumps({"rid": request_id, "ip": client_ip()})

    def verify_confirm_token(token: str, max_age: int = 300) -> str:
        """Return rid if token is valid, otherwise raise."""
        data = serializer.loads(token, max_age=max_age)
        if data.get("ip") != client_ip():
            raise BadSignature("IP mismatch")
        return data["rid"]
    
    # --------------------------------------------------
    # EDIT REQUEST SESSION HANDLING
    # --------------------------------------------------

    EDIT_WINDOW_SECS = 20 * 60          # 20 minutes

    def new_edit_token(request_id: str) -> str:
        """Signed 20-min token, bound to caller’s IP *and* request_id."""
        payload = {"rid": request_id, "ip": client_ip()}
        return serializer.dumps(payload)          # timestamp is implicit

    def verify_edit_token(token: str, request_id: str) -> bool:
        """True ⇢ token is intact, <20 min old, from same IP & matches id."""
        try:
            data = serializer.loads(token, max_age=EDIT_WINDOW_SECS)
            return data["ip"] == client_ip() and data["rid"] == request_id
        except (BadSignature, SignatureExpired):
            return False
    # --------------------------------------------------
    # START APPLICATION ENDPOINTS
    # --------------------------------------------------


    @app.route('/', methods=['GET'])
    def home():
        current_app.logger.info("GET / - Rendering landing page.")
        return render_template('landing.html')
    
    @app.route('/textile-waste', methods=['GET'])
    def textileWaste():
        current_app.logger.info("GET /textile-waste - Rendering textile_waste page.")
        return render_template('textile_waste.html')
    
    @app.route('/about', methods=['GET'])
    def about():
        current_app.logger.info("GET /about - Rendering about page.")
        return render_template('about.html')
    
    @app.route('/contact', methods=['GET'])
    def contact():
        current_app.logger.info("GET /contact - Rendering contact page.")
        return render_template('contact.html')

    @app.route('/drop-boxes', methods=['GET'])
    def dropBoxes():
        current_app.logger.info("GET /drop-boxes - Rendering drop boxes page.")
        return render_template('drop_boxes.html')
    


    # --------------------------------------------------

    # START REQUEST FLOW

    # --------------------------------------------------

    @app.route('/verify_zip', methods=['GET'])
    @limiter.limit("60 per hour")
    def verify_zip():
        current_app.logger.debug("GET /verify_zip - verifying user zip.")

        zip_code = request.args.get('zipcode')
        current_app.logger.debug("Zip code provided: %s", zip_code)

        approved_zips = ["94566", "94568", "94588", "94568", "94550", "94551", "94582", "94583", "94506", "94526"] 
        result = verifyZip(approved_zips, zip_code)
        current_app.logger.debug("verifyZip result: %s", result)

        return jsonify(result)
    
    @app.post("/api/validate_address")
    @limiter.limit("20 per hour")
    def validate_address():
        log = current_app.logger
        log.debug("POST /api/validate_address – verifying user address.")

        # ③ token check -------------------------------------------------------
        validate_csrf(request.headers.get("X-CSRFToken", ""))

        # 1️⃣ Extract body --------------------------------------------------
        data = request.get_json(force=True) or {}
        full_addr = data.get("full_addr")
        place_id  = data.get("place_id")
        city      = data.get("city")
        zip_code  = data.get("zip")

        # 2️⃣ Sanity-check payload (short-circuit before hitting Google) ----
        if not all((full_addr, city, zip_code)):
            # Still HTTP-200 so the JS can show the message in-line
            return jsonify(valid=False,
                        message="Address, city and ZIP are required."), 200

        # 3️⃣ Call the validator -------------------------------------------
        try:
            ok, msg = verifyAddress(full_addr, place_id, city, zip_code)
        except AddressError as ae:
            # Google service down / quota exhausted, etc.
            # Preserve front-end expectations: valid:false, HTTP-200
            current_app.logger.error("Validate address endpoint error: %s", ae)
            return jsonify(valid=False, message=str(ae)), 200
        except Exception:                           # truly unexpected
            log.exception("Unexpected error in validate_address")
            return jsonify(valid=False,
                        message="Internal server error"), 500

        # 4️⃣ Bubble result back unchanged ---------------------------------
        return jsonify(valid=ok, message=msg), 200



    @app.route('/request_pickup')
    @limiter.limit("20 per hour")
    def request_pickup():
        current_app.logger.info("GET /request_pickup - User accessed request_pickup page.")
        form = RequestForm()
        zipcode = request.args.get('zipcode')
        ZIP_TO_CITY = {
            "94566": "Pleasanton",
            "94568": "Dublin",
            "94588": "Pleasanton",
            "94550": "Livermore",
            "94551": "Livermore"
        }
        current_app.logger.debug("Checking user's zipcode: %s", zipcode)

        if zipcode in ZIP_TO_CITY:
            city = ZIP_TO_CITY[zipcode]
        else:
            city = None
            zipcode = None
            current_app.logger.warning("Invalid or missing zipcode provided: %s", zipcode)

        return render_template('request.html', zipcode = zipcode, city=city, form=form, GOOGLE_API_KEY=GOOGLE_API_KEY)


    @app.route('/request_init', methods=['GET', 'POST'])
    @limiter.limit("10 per hour")
    def request_init():
        form = RequestForm()
        if form.validate_on_submit():
            current_app.logger.info("POST /request_init - Form validated successfully. Creating new request.")
            # Extract form data
            fname   = form.firstName.data
            lname   = form.lastName.data
            email   = form.email.data
            phone   = form.phone.data
            address = form.address.data
            address2 = form.secondaryAddress.data
            city    = form.city.data
            zip_    = form.zip.data
            notes   = form.notes.data
            awareness = form.awarenessOptions.data
            date_filed = date.today()

            gated = form.gated.data

            token = os.getenv("MAPBOX_ACCESS_TOKEN")
            if not token:
                raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")

            # build one full address string
            full_address = ", ".join(filter(None, [address, city, "CA", zip_]))
            try:
                geocoded_addr = _maybe_geocode(full_address, token)
            except Exception as e:
                current_app.logger.error("Geocoding failed for %r: %s", full_address, e)
                # fallback to raw address string (or handle as you prefer)
                geocoded_addr = None
            
            current_app.logger.debug("New request created.")
            
            # Insert into DB (assuming add_request is defined elsewhere)
            new_id = add_request(
                date_filed = date_filed,
                fname=fname,
                lname=lname,
                email=email,
                phone_number=phone,
                address=address,
                address2 = address2,
                city=city,
                zipcode=zip_,
                geocoded_addr = geocoded_addr,
                notes=notes,
                gated=gated,
                awareness=awareness,
                status="Unfinished"
            )
            pickup = db.session.get(PickupRequest, new_id)
            pickup_code = pickup.request_id
            current_app.logger.info("New pickup request created.")
            session.clear()                               # blow away any old pickup flow
            token = new_confirm_token(pickup_code)
            session.update({
                "pickup_request_id": pickup_code,
                "confirm_token":    token,
                "confirm_expires":  time.time() + 300     # 5 minute page-refresh window
            })
            return redirect(url_for('select_date', request_id=pickup_code))
        
        if request.method == 'POST':
            current_app.logger.warning("POST /request_init - Form validation failed. Errors: %s", form.errors)

        current_app.logger.info("GET /request_init - Rendering request form.")
        return render_template('request.html', form=form, GOOGLE_API_KEY=GOOGLE_API_KEY)


    @app.route('/date', methods=['GET', 'POST'])
    @limiter.limit("30 per hour")
    def select_date():
        request_id = request.args.get('request_id')
        token      = session.get('confirm_token')

        current_app.logger.debug("Select date route accessed with request_id=%s", request_id)

        # ── 1) Session must still be alive and point at the same request  ──
        if session.get("pickup_request_id") != request_id:
            current_app.logger.error("Session mismatch for /select-date")
            abort(404)

        # ── 2) Token must verify, be <5 min old, and come from same IP ──
        try:
            verify_confirm_token(token)
        except (SignatureExpired, BadSignature, TypeError):
            current_app.logger.warning("Missing or invalid confirm token")
            return render_template('440.html')

        # ── 3) Extra clock-based guard (belt-and-braces) ──
        if time.time() > session.get("confirm_expires", 0):
            current_app.logger.info("Confirm window elapsed – clearing session")
            session.clear()
            return render_template('440.html')
        current_app.logger.debug("select_date route accessed with request_id=%s", request_id)

        if not request_id:
            current_app.logger.warning("No request_id in query parameters; session may have expired.")
            return "Session expired, please restart.", 400

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        if not pickup:
            current_app.logger.warning("PickupRequest not found for request_id=%s", request_id)
            abort(404)

        offset = request.args.get('week_offset', default=0, type=int)
        if offset < 0: 
            offset = 0
        if offset > 2: 
            offset = 2

        days_list, base_date_str = build_schedule(offset)
        current_app.logger.debug("Built schedule and sending to /select-date")
        form = DateSelectionForm()

        if form.validate_on_submit():
            chosen_date = form.chosen_date.data  # e.g., "2025-01-11"
            chosen_time = form.chosen_time.data  # e.g., "08:00-16:00"

            pickup.request_date = chosen_date
            pickup.request_time = chosen_time
            pickup.status = "Requested"
            pickup.date_filed = date.today()
            db.session.commit()
            current_app.logger.info(
                "Pickup request %s updated with chosen_date=%s, chosen_time=%s. Redirecting to confirmation.",
                request_id, chosen_date, chosen_time
            )

            session['pickup_request_id'] = request_id

            # if session.get('confirmation_email_sent') and session["pickup_request_id"] == pickup.request_id:
            #     current_app.logger.info("Sending edited pickup request email for request_id=%s", request_id)
            #     send_edited_request_email(pickup)
            #     current_app.logger.debug("Edited pickup request email sent for request_id=%s", request_id)
            #     token = new_confirm_token(request_id)
            #     session.update({
            #         "pickup_request_id": request_id,
            #         "confirm_token":    token,
            #         "confirm_expires":  time.time() + 300     # 5 minute page-refresh window
            #     })
            #     return redirect(url_for('confirmation',
            #                         request_id=request_id,
            #                         t=token))  
            # else:
            current_app.logger.info("Confirmation email not yet sent for request_id=%s, sending to confirmation page", request_id)
            return redirect(url_for('confirmation',
                                request_id=request_id))  
        
        current_app.logger.info(
            "User is selecting a date/time for request_id=%s, offset=%d. Rendering select_date.html.",
            request_id, offset
        )

        return render_template('select_date.html',
                            form=form,
                            pickup=pickup,
                            days_list=days_list,
                            offset=offset,
                            max_offset=2,
                            request_id=request_id,
                            base_date_str=base_date_str)
    
    @app.route('/confirmation')
    @limiter.limit("30 per hour")
    def confirmation():
        request_id = request.args.get('request_id')
        token      = session.get('confirm_token')

        current_app.logger.debug("Confirmation route accessed with request_id=%s", request_id)

        # ── 1) Session must still be alive and point at the same request  ──
        if session.get("pickup_request_id") != request_id:
            current_app.logger.error("Session mismatch for /confirmation")
            abort(404)

        # ── 2) Token must verify, be <5 min old, and come from same IP ──
        try:
            verify_confirm_token(token)
        except (SignatureExpired, BadSignature, TypeError):
            current_app.logger.warning("Missing or invalid confirm token")
            return render_template('440.html')

        # ── 3) Extra clock-based guard (belt-and-braces) ──
        if time.time() > session.get("confirm_expires", 0):
            current_app.logger.info("Confirm window elapsed – clearing session")
            session.clear()
            return render_template('440.html')

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        if pickup is None:
            current_app.logger.warning("No PickupRequest found for request_id=%s in confirmation route.", request_id)
            abort(404)

        current_app.logger.info("Sending pickup request email for request_id=%s", request_id)

        if not session.get('confirmation_email_sent'):
            current_app.logger.info("Sending pickup request email for request_id=%s", request_id)
            send_request_email(pickup)
            session['confirmation_email_sent'] = True
            current_app.logger.debug("Pickup request email sent for request_id=%s", request_id)
        else:
            current_app.logger.info("Confirmation email already sent for request_id=%s", request_id)

        current_app.logger.info("Rendering confirmation.html for request_id=%s", request_id)

        return render_template('confirmation.html', pickup=pickup, request_id=pickup.request_id)


    @app.route('/update_address', methods=['POST'])
    @approval_scope
    @code_email_scope
    def update_address():
        form = UpdateAddressForm()
        if not form.validate_on_submit():
            current_app.logger.error(
                "Form validation failed for update_address. Errors: %s", form.errors
            )
            return jsonify({"status": "error",
                            "message": "Invalid form submission."}), 400

        # ─── 1. Get the new pieces ───────────────────────────────────────────
        request_id = form.request_id.data
        address    = form.address.data
        address2   = form.address2.data
        city       = form.city.data
        zip_code   = form.zipcode.data
        current_app.logger.info(
            "Received valid POST to update address for request_id=%s", request_id
        )

        # ─── 2. Find the row ─────────────────────────────────────────────────
        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        if not pickup:
            current_app.logger.warning(
                "No PickupRequest found for request_id=%s", request_id
            )
            return jsonify({"status": "error",
                            "message": f"No record found for request_id={request_id}"}), 400

        # ─── 3. Update plain‑text fields ─────────────────────────────────────
        pickup.address  = address
        pickup.address2 = address2
        pickup.city     = city
        pickup.zipcode  = zip_code

        # ─── 4. Geocode the *new* full address  ──────────────────────────────
        full_addr = ", ".join(filter(None, [address, address2, city, zip_code]))
        geocoded = None
        try:
            token = os.getenv("MAPBOX_ACCESS_TOKEN")
            if not token:
                raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")
            geocoded = _maybe_geocode(full_addr, token)
            # optional: strip whitespace
            if geocoded and _coords_like(geocoded):
                geocoded = geocoded.replace(" ", "")
            current_app.logger.debug("Geocoded address")
        except Exception as e:
            # Don’t block the update; just log.
            current_app.logger.error("Geocoding failed for request ID: %s", request_id)

        pickup.geocoded_addr = geocoded    # may be None if failure

        # ─── 5. Commit & notify ──────────────────────────────────────────────
        db.session.commit()
        current_app.logger.info(
            "Successfully updated address (and geocode) for request_id=%s", request_id
        )

        #send_edited_request_email(pickup)
        current_app.logger.debug("Edited‑request email sent for request_id=%s", request_id)

        return redirect(url_for('edit_request', request_id=request_id))

    @app.route('/submit-rating', methods=['POST'])
    @limiter.limit("5 per hour")
    def submit_rating():
        current_app.logger.info("POST /submit-rating - User rating their experience on the platform.")
        form = RatingForm()
        return

    # --------------------------------------------------

    # START EDIT REQUEST FLOW

    # --------------------------------------------------



    @app.route('/edit-request-init', methods=['GET'])
    @limiter.limit("20 per hour")
    def edit_request_init():
        current_app.logger.info("GET /edit-request-init - User accessing the edit request initialization page.")
        edit_request_form = EditRequestInitForm()
        return render_template(
            'edit_request.html',
            edit_request_form=edit_request_form,
            partial="/partials/_editRequest_init.html"
        )


    def can_edit(request_id: str, email: str):
        """
        Central authority for all business rules that gate an edit.

        Returns
        -------
        (True,  pickup)         – all checks passed
        (False, error_message)  – failed, give the reason that should be shown
        """
        request_id = request_id.strip().upper()

        # 1) basic format
        if len(request_id) != 8:
            return False, (
                "Your code must be exactly 8 digits. "
                "Please double-check and try again."
            )

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        if not pickup:
            return False, (
                "Request not found. Please make sure the confirmation number "
                "matches exactly what appears in your confirmation email."
            )

        # 2) email must match
        if pickup.email != email:
            return False, (
                "Request not found. Please make sure the confirmation number "
                "matches exactly what appears in your confirmation email."
            )

        # 4) date checks
        if pickup.request_date:
            try:
                req_date = datetime.strptime(pickup.request_date, '%Y-%m-%d').date()
                today = datetime.now().date()

                #no same-day edits
                if req_date == today:
                    return False, (
                        "Sorry, requests cannot be edited on the day of pickup. "
                        "Please contact us if there is an urgent change needed for your request."
                    )

                # no edits once the date has passed
                if req_date < today:
                    return False, (
                        "The date you requested for your pickup has already passed and can’t be edited."
                    )

            except ValueError:
                current_app.logger.warning("Bad date on request %s", request_id)
                return False, (
                    "We couldn’t verify the request date. Please contact us."
                )

        # 4) status checks
        if pickup.status in ("Cancelled", "Completed"):
            return False, f"Your request has been {pickup.status.lower()} and cannot be edited."

        return True, pickup
    
    @app.route('/edit-request-approval', methods=['POST'])
    @approval_scope
    @code_email_scope
    def edit_request_approval():
        """Receives the code+email form, validates via can_edit(), and
        either shows the edit screen or bounces back with a flash alert."""
        current_app.logger.info("POST /edit-request-approval - User accessing the edit request page.")

        form = EditRequestInitForm()

        if not form.validate_on_submit():
            flash("Invalid form submission. Verify that you clicked the 'I'm not a robot' box.", 'danger')
            current_app.logger.warning("Invalid form submission at edit_request")
            return redirect(url_for('edit_request_init'))

        ok, result = can_edit(form.request_id.data, form.requester_email.data)
        if not ok:
            current_app.logger.warning("edit_request endpoint hit, email and request ID don't match. Request ID = %s", form.request_id.data)
            flash(result, 'warning')
            return redirect(url_for('edit_request_init'))

        # ── All checks passed ────────────────────────────────────────────
        current_app.logger.info("Request to edit valid, rendering edit request page.")

        pickup = result

        token = new_edit_token(pickup.request_id)
        session.update({
            "edit_token":   token,
            "edit_expires": time.time() + EDIT_WINDOW_SECS,
        })

        return redirect(url_for('edit_request', request_id = pickup.request_id))
    
    @app.route('/edit-request', methods=['GET'])
    @in_window_scope
    @edit_window_required
    def edit_request():
        """Receives the code+email form, validates via can_edit(), and
        either shows the edit screen or bounces back with a flash alert."""
        current_app.logger.info("POST /edit-request - User accessing the edit request page.")

        request_id = request.args.get('request_id')

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()

        update_form = UpdateAddressForm(obj=pickup)
        update_form.request_id.data = pickup.request_id
        update_form.page.data = "edit_request"

        cancel_form = CancelRequestForm()
        cancel_form.request_id.data = pickup.request_id

        notes_form = updateCustomerNotes()
        notes_form.request_id.data = pickup.request_id
        notes_form.notes.data = pickup.notes

        return render_template(
            'edit_request.html',
            partial="/partials/_editRequest_info.html",
            pickup=pickup,
            max_offset=2,
            request_id=pickup.request_id,
            form=update_form,
            cancel_form=cancel_form,
            notes_form=notes_form
        )
        
    @app.route('/edit-request-time', methods=['GET'])
    @in_window_scope
    @edit_window_required
    def edit_request_time():
        current_app.logger.debug("GET /edit-request-time - user attempting to edit request time.")

        time_form = EditRequestTimeForm()
        request_id = request.args.get('request_id')
        if not request_id:
            current_app.logger.warning("No request_id provided in query string; session may have expired.")
            return "Session expired, please restart.", 400

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        time_form.request_id.data = pickup.request_id
        if not pickup:
            current_app.logger.warning("PickupRequest not found for request_id=%s", request_id)
            abort(404)

        offset = request.args.get('week_offset', default=0, type=int)
        if offset < 0: 
            offset = 0
        if offset > 2: 
            offset = 2

        offset = request.args.get('week_offset', default=0, type=int)
        
        days_list, base_date_str = build_schedule(offset)
        current_app.logger.debug(
            "Built schedule and routing to edit_request"
        )

        update_address_form = UpdateAddressForm(obj=pickup)

        cancel_form = CancelRequestForm()
        cancel_form.request_id.data = pickup.request_id

        notes_form = updateCustomerNotes()
        notes_form.request_id.data = pickup.request_id
        notes_form.notes.data = pickup.notes

        current_app.logger.info("Rendering edit_request.html for request_id=%s to edit time.", request_id)

        return render_template('edit_request.html', 
                            partial="/partials/_editRequest_info.html", 
                            edit_request="/partials/_editRequest_editTime.html",                             
                            pickup=pickup,
                            days_list=days_list,
                            offset=offset,
                            max_offset=2,
                            request_id=request_id,
                            base_date_str = base_date_str,
                            form = update_address_form,
                            time_form=time_form,
                            notes_form=notes_form,
                            cancel_form=cancel_form)
    
    @app.route('/edit-request-time-submit', methods=['POST'])
    @in_window_scope
    @edit_window_required
    def edit_request_time_submit():
        current_app.logger.debug("POST /edit-request-time-submit - handling time edit form submission.")

        form = EditRequestTimeForm()
        print("at form")
        if form.validate_on_submit():
            current_app.logger.debug("Form validated successfully for editing request time.")

            print("form valid")
            request_id = form.request_id.data
            chosen_date = datetime.strptime(form.chosen_date.data, "%Y-%m-%d").date()
            chosen_time = form.chosen_time.data

            pickup = PickupRequest.query.filter_by(request_id=request_id).first()
            if not pickup:
                current_app.logger.warning("No pickup found for request_id=%s, redirecting to edit_request.", request_id)

                return redirect(url_for('edit_request'))
            
            pickup.request_date = chosen_date
            pickup.request_time = chosen_time
            pickup.status = "Requested"
            pickup.date_filed = date.today()
            db.session.commit()

            current_app.logger.info(
                "Pickup request %s time updated to (%s, %s). Sending edited request email.",
                request_id, chosen_date, chosen_time
            )

            #send_edited_request_email(pickup)

            return redirect(url_for('edit_request', request_id = pickup.request_id))
        else:
            current_app.logger.warning("Form validation failed for edit-request-time-submit. Errors: %s", form.errors)
            # Optionally log or flash the errors from form.errors here for debugging
            return redirect(url_for('edit_request_init'))
    
    @app.route("/edit-request/<string:pickup_id>/notes", methods=["POST"])
    @in_window_scope
    @edit_window_required
    def edit_request_notes(pickup_id: str):
        """
        Persist the admin note for a single pickup, then redirect back.
        """
        current_app.logger.debug("Request id %s attempting to edit notes.", pickup_id)

        form = updateCustomerNotes()
        if not form.validate_on_submit():
            current_app.logger.warning("Updating notes failed, form invalid.")
            flash("Your notes are too long—please restrict to 400 characters or less.", "warning")
            return redirect(url_for("edit_request", request_id=pickup_id))

        try:
            current_app.logger.debug("Note update form validated, attempting to add to the DB.")
            pickup = PickupRequest.query.filter_by(request_id=pickup_id).first()
            if pickup is None:
                current_app.logger.warning("Attempted to save notes for non-existent pickup %s.", pickup_id)
                abort(404, description="Pickup not found.")

            pickup.notes = form.notes.data
            db.session.commit()
            current_app.logger.debug("Successfully added notes to DB.")


        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Failed to update notes for pickup %s.", pickup_id)
            flash("Database error—could not save notes.", "error")
            return "Error updating notes.", 404
        send_edited_request_email(pickup)
        current_app.logger.debug("Updated request email sent for request ID: %s", pickup_id)
        session.clear()
        flash("Your pickup details have been updated and a confirmation email has been sent.", "success")
        return redirect(url_for('edit_request_init'))

    
    @app.route('/cancel-request', methods=["POST"])
    @in_window_scope
    @edit_window_required
    def cancel_request():
        current_app.logger.debug("POST /cancel-request - user attempting to cancel request.")

        form = CancelRequestForm()
        if form.validate_on_submit():
            request_id = form.request_id.data
            current_app.logger.info("CancelRequestForm validated. request_id=%s", request_id)

            pickup = PickupRequest.query.filter_by(request_id=request_id).first()

            if not pickup:
                current_app.logger.warning("No pickup found for request_id=%s while attempting to cancel.", request_id)
                return jsonify({
                    "valid": False,
                    "reason": "Pickup not found."
                }), 404
            
            pickup.status = "Cancelled"
            db.session.commit()
            if pickup.status == "Cancelled":
                current_app.logger.info(
                    "Request for request_id=%s successfully changed to Cancelled.",
                    request_id
                )
                send_cancellation_email(pickup)
                current_app.logger.debug(
                    "Cancellation email sent for request ID: %s",
                    request_id
                )
                return jsonify({
                    "valid": True,
                    "reason": "Your pickup request has been cancelled. We have sent you an email confirmation."
                })
            else:
                current_app.logger.warning("Pickup status failed to update to Cancelled for request_id=%s.", request_id)
                return jsonify({
                    "valid": False,
                    "reason": "Unable to cancel your request. Please contact us for further support."
                })
        else:
            current_app.logger.warning("Form validation failed for cancel-request. Errors: %s", form.errors)
            return jsonify({
                "valid": False,
                "reason": "Invalid form submission.",
                "errors": form.errors
            }), 400

    # --------------------------------------------------

    # ADMIN ENDPOINTS AND FUNCTIONS

    # --------------------------------------------------



    @app.route('/admin')
    def admin():
        current_app.logger.info("GET /admin - User accessed admin route; redirecting to admin_console.")
        return redirect(url_for('admin_console'))
    
    @app.route("/admin/login")
    @limiter.limit("10 per hour")
    def admin_login():
        redirect_uri = url_for(
            "callback",
            _external=True,
            _scheme="https" if CONFIG_NAME != "development" else "http"
        )

        resp = oauth.oidc.authorize_redirect(redirect_uri)

        # ---------- make the 302 un-cacheable ----------
        resp.headers["Cache-Control"] = "no-store, private"
        resp.headers["Pragma"]        = "no-cache"
        # ----------------------------------------------
        return resp
    
    @app.route("/callback")
    @limiter.limit("10 per hour")
    def callback():
        """Cognito redirects back here with ?code= ; exchange it for tokens."""
        current_app.logger.info("GET /callback – exchanging code for tokens")

        token = oauth.oidc.authorize_access_token()  # state + PKCE automatically verified

        # --------------------------------------------------------------------------
        # Extra defence: verify the ID-token signature & claims ourselves :contentReference[oaicite:1]{index=1}
        # --------------------------------------------------------------------------
        try:
            jwks_uri = oauth.oidc.load_server_metadata()["jwks_uri"]
            jwks     = JsonWebKey.import_key_set(requests.get(jwks_uri, timeout=5).json())
            id_token = jwt.decode(token["id_token"], jwks)  # verifies signature
            id_token.validate()                            # exp, iat, aud, iss…
        except Exception as exc:
            record_login_failure()
            current_app.logger.exception("ID-token validation failed: %s", exc)
            return "Invalid id_token", 400

        # Persist only what you really need
        session.permanent = True
        session["id_token"]  = token["id_token"]
        session["expires_at"] = id_token["exp"]

        current_app.logger.info("Admin logged in.")

        return redirect(url_for("admin_console"))


    @app.route("/logout")
    def admin_logout():
        session.clear()                               # 1. Drop everything we stored

        logout_uri = url_for("home", _external=True,
                            _scheme="https" if CONFIG_NAME != "development" else "http")
        print(logout_uri)

        cognito_logout = (
            f"https://{COGNITO_DOMAIN}/logout"
            f"?client_id={COGNITO_CLIENT_ID}"
            f"&logout_uri={quote_plus(logout_uri)}"
            f"&federated"
        )
        return redirect(cognito_logout)  
        
    @app.route('/admin-console', methods=['GET', 'POST'])
    @login_required
    def admin_console():
        current_app.logger.info("Accessing /admin-console.")

        today = datetime.today().date()
        # Default to the current week: from Monday to today.
        today = date.today()
        default_start_date = today - timedelta(days=7)
        default_end_date   = today

        form = DateRangeForm()

        # Process form submission
        if form.validate_on_submit():
            start_date = form.start_date.data
            end_date = form.end_date.data
            current_app.logger.debug("DateRangeForm submitted. start_date=%s, end_date=%s", start_date, end_date)

        else:
            # On GET (or if validation fails), use default dates
            start_date = default_start_date
            end_date = default_end_date
            # Pre-populate the form fields with default dates
            form.start_date.data = start_date
            form.end_date.data = end_date
            current_app.logger.debug("Using default date range for admin_console.")

        # Build the complete date range for the period
        num_days = (end_date - start_date).days + 1
        date_range = [start_date + timedelta(days=i) for i in range(num_days)]
        daily_counts_dict = {d.strftime("%Y-%m-%d"): 0 for d in date_range}

        # Query daily pickup counts within the chosen range.
        query_result = db.session.query(
            PickupRequest.date_filed,
            db.func.count(PickupRequest.id)
        ).filter(
            PickupRequest.date_filed >= start_date.strftime("%Y-%m-%d"),
            PickupRequest.date_filed <= end_date.strftime("%Y-%m-%d")
        ).group_by(
            PickupRequest.date_filed
        ).order_by(
            PickupRequest.date_filed
        ).all()

        for row in query_result:
            daily_counts_dict[row[0]] = row[1]

        # Convert to a JSON-serializable list of [date, count] pairs.
        daily_counts = [[d.strftime("%Y-%m-%d"), daily_counts_dict[d.strftime("%Y-%m-%d")]] for d in date_range]

        # Calculate total pickups for the same date range.
        pickups_total = PickupRequest.query.filter(
            PickupRequest.date_filed >= start_date.strftime("%Y-%m-%d"),
            PickupRequest.date_filed <= end_date.strftime("%Y-%m-%d")
        ).count()

        pickups_total_all = db.session.query(db.func.count(PickupRequest.id)).scalar()


        current_app.logger.debug(
            "Window total=%d, All-time total=%d, date range %s – %s",
            pickups_total, pickups_total_all, start_date, end_date
        )
        metrics          = get_admin_metrics(start_date, end_date)
        city_stats       = city_distribution(start_date, end_date)
        awareness_stats  = awareness_distribution(start_date, end_date)

        return render_template(
            'admin/admin_console.html',
            daily_counts=daily_counts,
            pickups_total_window=pickups_total,
            pickups_total_all=pickups_total_all,
            metrics=metrics,
            city_stats=city_stats, 
            awareness_stats = awareness_stats,
            form=form  # Pass the form to your template
        )

    @app.route('/admin-schedule', methods=['GET', 'POST'])
    @login_required
    def admin_schedule():
        current_app.logger.info("Accessing /admin-schedule.")

        schedule_data = get_service_schedule()
        address = get_address()
        admin_schedule_form = AdminScheduleForm()
        admin_address_form = AdminAddressForm()

        # Populate the schedule form on GET
        if request.method == 'GET':
            current_app.logger.debug("GET request to /admin-schedule. Populating forms with current schedule data.")

            for i, sched in enumerate(schedule_data):
                if i < len(admin_schedule_form.days):
                    admin_schedule_form.days[i].record_id.data = sched.id
                    admin_schedule_form.days[i].is_available.data = sched.is_available
            admin_address_form.admin_address.data = address

        # Process the POSTs—here you might want to distinguish which form is being submitted
        if request.method == 'POST':
            current_app.logger.debug("POST request to /admin-schedule. Checking which form was submitted.")

            # Check which submit button was pressed.
            if admin_schedule_form.submit.data and admin_schedule_form.validate_on_submit():
                current_app.logger.info("AdminScheduleForm was submitted and validated.")

                for day_form in admin_schedule_form.days:
                    record_id = day_form.record_id.data
                    is_available = day_form.is_available.data
                    schedule_record = db.session.get(ServiceSchedule, record_id)
                    if schedule_record:
                        schedule_record.is_available = is_available
                        schedule_record.slot1_start  = "08:00"
                        schedule_record.slot1_end    = "16:00"
                        schedule_record.slot2_start  = ""
                        schedule_record.slot2_end    = ""
                db.session.commit()
                current_app.logger.info("Schedule data updated; redirecting to /admin-schedule.")

                return redirect(url_for('admin_schedule'))
            
            else:
                current_app.logger.warning("POST to /admin-schedule but neither form validated successfully. Errors: %s, %s",
                                            admin_schedule_form.errors, admin_address_form.errors)
            
        zipped_data = list(zip(admin_schedule_form.days, schedule_data))
        current_app.logger.debug("Rendering admin_schedule.html with schedule_data and forms.")

        return render_template(
            'admin/admin_schedule.html',
            schedule_data=schedule_data,
            address=address,
            admin_schedule_form=admin_schedule_form,
            admin_address_form=admin_address_form,
            zipped_data=zipped_data
        )

    

    @app.route('/admin-set-address', methods=["POST"])
    @login_required
    def admin_set_address():
        current_app.logger.info("POST /admin-set-address - Admin attempting to set the address.")
        form = AdminAddressForm()

        if not form.validate_on_submit():
            current_app.logger.warning(
                "Form validation failed in admin_set_address. Errors: %s",
                form.errors
            )
            return redirect(url_for('admin_schedule'))

        # 1) Get the new text address
        new_address = form.admin_address.data
        current_app.logger.debug("Form validated. New address: %r", new_address)

        # 2) Persist the raw text under key "admin_address"
        admin_cfg = DBConfig.query.filter_by(key='admin_address').first()
        if admin_cfg:
            admin_cfg.value = new_address
            current_app.logger.debug("Updated existing admin_address config.")
        else:
            admin_cfg = DBConfig(key='admin_address', value=new_address)
            db.session.add(admin_cfg)
            current_app.logger.debug("Created new admin_address config.")

        # 3) Geocode it
        token = os.getenv("MAPBOX_ACCESS_TOKEN")
        if not token:
            raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")
        try:
            # if you want to include city/zip you can expand new_address here
            geocoded = _maybe_geocode(new_address, token)
            current_app.logger.debug("Geocoded admin address to %r", geocoded)
        except Exception as e:
            current_app.logger.error(
                "Failed to geocode admin_address %r: %s", new_address, e
            )
            geocoded = None

        # 4) Persist the geocode under key "geocoded_admin_addr"
        geo_cfg = DBConfig.query.filter_by(key='geocoded_admin_addr').first()
        if geo_cfg:
            geo_cfg.value = geocoded
            current_app.logger.debug("Updated existing geocoded_admin_addr config.")
        else:
            geo_cfg = DBConfig(key='geocoded_admin_addr', value=geocoded)
            db.session.add(geo_cfg)
            current_app.logger.debug("Created new geocoded_admin_addr config.")

        # 5) Commit once, then redirect
        db.session.commit()
        current_app.logger.info("Admin address and geocode updated. Redirecting.")
        return redirect(url_for('admin_schedule'))


    @app.route('/admin-pickups', methods=['GET', 'POST'])
    @login_required
    def admin_pickups():
        current_app.logger.info("Accessing /admin-pickups page.")

        delete_form = DeletePickupForm()
        schedule_data = get_service_schedule()

        # Start with a base query for PickupRequest
        query = PickupRequest.query

        # Apply status filter if provided
        status_filter = request.args.get('status_filter')
        if status_filter:
            current_app.logger.debug("Filtering pickups by status=%s", status_filter)
            query = query.filter(PickupRequest.status == status_filter)

        # Apply date range filters (assuming you are filtering by date_filed)
        start_date = request.args.get('start_date')
        if start_date:
            current_app.logger.debug("Filtering pickups by request_date >= %s", start_date)
            query = query.filter(PickupRequest.request_date >= start_date)
        end_date = request.args.get('end_date')
        if end_date:
            current_app.logger.debug("Filtering pickups by request_date <= %s", end_date)
            query = query.filter(PickupRequest.request_date <= end_date)

        # Apply sorting based on user selection
        sort_mapping = {
            'date_filed'     : PickupRequest.date_filed,
            'date_requested': PickupRequest.request_date,
        }
        sort_key    = request.args.get('sort_by', 'date_filed')
        sort_column = sort_mapping.get(sort_key, PickupRequest.date_filed)

        query = query.order_by(sort_column.desc(), PickupRequest.id.desc())

        requests = query.all()
        current_app.logger.debug("Found %d pickup requests after applying filters/sorts.", len(requests))
        cleanup_form = CleanPickupsForm()

        return render_template('admin/admin_pickups.html', schedule_data=schedule_data, requests=requests, delete_form=delete_form, cleanup_form=cleanup_form)
    
    def format_iso_to_pretty(date_str: str) -> str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%B %-d, %Y")      # on Linux/Mac the “-” drops leading zeros
            # on Windows you may need "%B %#d, %Y"
        except (ValueError, TypeError):
            return date_str  # fallback if it’s not in the right form

    @app.route("/individual-pickup/<string:pickup_id>", methods=["GET"])
    @login_required
    def individual_pickup(pickup_id: str):
        """
        Render the individual-pickup view.
        """
        current_app.logger.info("GET /admin/individual_pickup - Admin viewing a pickup.")

        # ── Fetch the pickup safely ──────────────────────────────────────────────
        try:
            pickup = PickupRequest.query.filter_by(request_id=pickup_id).first()
        except Exception as exc:
            current_app.logger.exception("Failed to fetch pickup.")
            return redirect(url_for('admin_pickups'))

        if pickup is None:
            current_app.logger.warning("Pickup %s not found.", pickup_id)
            return redirect(url_for('admin_pickups'))

        # ── Instantiate the form (empty on GET) ──────────────────────────────────
        form = AddPickupNotes(obj=pickup)  # pre-fill if you store notes on model
        # in your view/controller
        pickup.date_filed_pretty   = format_iso_to_pretty(pickup.date_filed)
        pickup.request_date_pretty = format_iso_to_pretty(pickup.request_date)

        return render_template(
            "admin/admin_ind_pickup.html",
            pickup=pickup,
            admin_notes_form=form,
        )

    @app.route("/individual-pickup/<string:pickup_id>/notes", methods=["POST"])
    @login_required
    def save_admin_notes(pickup_id: str):
        """
        Persist the admin note for a single pickup, then redirect back.
        """
        print(pickup_id)
        form = AddPickupNotes()
        if not form.validate_on_submit():
            flash("Invalid form data; please correct and try again.", "error")
            return redirect(url_for("individual_pickup", pickup_id=pickup_id))

        try:
            pickup = PickupRequest.query.filter_by(request_id=pickup_id).first()
            if pickup is None:
                current_app.logger.warning("Attempted to save notes for non-existent pickup %s.", pickup_id)
                abort(404, description="Pickup not found.")

            pickup.admin_notes = form.admin_notes.data
            db.session.commit()

            # current_app.logger.info(
            #     "Admin %s updated notes for pickup %s.", current_user.id, pickup_id
            # )
            # flash("Notes saved successfully.", "success")

        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Failed to update notes for pickup %s.", pickup_id)
            flash("Database error—could not save notes.", "error")

        return redirect(url_for("individual_pickup", pickup_id=pickup_id))

    @app.route('/admin/filtered_requests')
    @login_required
    def filtered_requests():
        current_app.logger.info("Accessing /admin/filtered_requests - AJAX partial update of pickups table.")

        query = PickupRequest.query
        delete_form = DeletePickupForm()

        # Status filter
        status_filter = request.args.get('status_filter')
        if status_filter:
            current_app.logger.debug("Filtering requests by status=%s", status_filter)
            query = query.filter(PickupRequest.status == status_filter)

        # Date range filters (assuming filtering by date_filed)
        start_date = request.args.get('start_date')
        if start_date:
            current_app.logger.debug("Filtering requests by date_filed >= %s", start_date)
            query = query.filter(PickupRequest.date_filed >= start_date)
        end_date = request.args.get('end_date')
        if end_date:
            current_app.logger.debug("Filtering requests by date_filed <= %s", end_date)
            query = query.filter(PickupRequest.date_filed <= end_date)

        # Sorting
        sort_by = request.args.get('sort_by')
        if sort_by == 'date_filed':
            current_app.logger.debug("Sorting by date_filed desc.")
            query = query.order_by(PickupRequest.date_filed.desc())
        elif sort_by == 'date_requested':
            current_app.logger.debug("Sorting by request_date desc.")
            query = query.order_by(PickupRequest.request_date.desc())
        else:
            current_app.logger.debug("No specific sorting provided, sorting by ID desc.")
            query = query.order_by(PickupRequest.id.desc())

        requests = query.all()
        current_app.logger.debug("Returning partial with %d requests after filtering.", len(requests))

        return render_template('admin/partials/_pickup_requests_table.html', requests=requests, delete_form=delete_form)
    
    @app.route('/admin/pickups/delete', methods=['POST'])
    @login_required
    def delete_pickup():
        current_app.logger.info("POST /admin/pickups/delete - Admin attempting to delete a pickup request.")

        form = DeletePickupForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
            current_app.logger.debug("Form validated. Deleting pickup with ID=%s", pickup_id)

            pickup = PickupRequest.query.get_or_404(pickup_id)
            
            db.session.delete(pickup)
            db.session.commit()
            current_app.logger.info("Pickup request %s deleted successfully.", pickup_id)

        else:
            current_app.logger.warning("Invalid form submission when attempting to delete pickup. Errors: %s", form.errors)
        
        return redirect(url_for('admin_pickups'))
    
    @app.route('/admin/clean_pickups', methods=["POST"])
    @login_required
    def clean_pickups():
        form = CleanPickupsForm()

        # Always validate *before* doing any work
        if not form.validate_on_submit():
            flash("Invalid form submission.", "warning")
            return redirect(url_for("admin_pickups"))

        current_app.logger.info("ADMIN: triggered /clean_pickups")

        try:
            weekly_export()
        except Exception as exc:
            current_app.logger.exception("weekly_export() failed")
            flash(f"Weekly export failed! Please contact Sean.", "danger")

        else:
            current_app.logger.info("weekly_export() completed")
            flash("Weekly export completed successfully.", "success")


        return redirect(url_for("admin_pickups"))
        


    # --------------------------------------------------

    # ADMIN ROUTING ENDPOINTS

    # --------------------------------------------------



    @app.route('/route-overview')
    @login_required
    def route_overview():
        current_app.logger.info("GET /route-overview - displaying route overview page.")

        today = date.today().strftime("%Y-%m-%d")

        # --- Upcoming Pickups ---
        current_app.logger.debug("Querying upcoming pickups on or after %s.", today)

        upcoming_rows = (
            db.session.query(
                PickupRequest.request_date,
                PickupRequest.request_time,
                func.count(PickupRequest.id).label('pickup_count')
            )
            .filter(PickupRequest.request_date >= today)
            .group_by(PickupRequest.request_date, PickupRequest.request_time)
            .order_by(PickupRequest.request_date.asc())
            .all()
        )

        # Group the upcoming results by date.
        upcoming_grouped = {}
        for row in upcoming_rows:
            date_str = row.request_date
            upcoming_grouped.setdefault(date_str, []).append({
                'timeframe': row.request_time,
                'count': row.pickup_count
            })
        current_app.logger.debug("Upcoming grouped pickups: %s", upcoming_grouped)

        # Sort upcoming dates ascending.
        upcoming_dates_sorted = sorted(upcoming_grouped.items(), key=lambda x: x[0])

        # Decide what goes in next_pickup vs. upcoming_dates
        next_pickup = None
        remaining_upcoming = []

        if upcoming_dates_sorted:
            first_date, first_timeframes = upcoming_dates_sorted[0]

            # ➜ Only promote to next_pickup if it's **today**
            if first_date == today:
                next_pickup = {
                    'date': first_date,
                    'formatted_date': format_date(first_date),
                    'timeframes': first_timeframes
                }
                # all other upcoming dates
                for date_str, timeframes in upcoming_dates_sorted[1:]:
                    remaining_upcoming.append({
                        'date': date_str,
                        'formatted_date': format_date(date_str),
                        'timeframes': timeframes
                    })
                current_app.logger.debug(
                    "Next pickup is today (%s); remaining upcoming count=%d",
                    first_date, len(remaining_upcoming)
                )
            else:
                # nothing today, so *everything* is just upcoming
                for date_str, timeframes in upcoming_dates_sorted:
                    remaining_upcoming.append({
                        'date': date_str,
                        'formatted_date': format_date(date_str),
                        'timeframes': timeframes
                    })
                current_app.logger.debug(
                    "No pickups today; upcoming count=%d",
                    len(remaining_upcoming)
                )
        else:
            current_app.logger.debug("No upcoming dates found.")

        # --- Past Pickups ---
        current_app.logger.debug("Querying past pickups before %s.", today)

        past_rows = (
            db.session.query(
                PickupRequest.request_date,
                PickupRequest.request_time,
                func.count(PickupRequest.id).label('pickup_count')
            )
            .filter(PickupRequest.request_date < today)
            .group_by(PickupRequest.request_date, PickupRequest.request_time)
            .order_by(PickupRequest.request_date.desc())
            .all()
        )

        past_grouped = {}
        for row in past_rows:
            date_str = row.request_date
            past_grouped.setdefault(date_str, []).append({
                'timeframe': row.request_time,
                'count': row.pickup_count
            })

        # Sort past dates descending.
        past_dates_final = [
            {
                'date': d,
                'formatted_date': format_date(d),
                'timeframes': tfs
            }
            for d, tfs in sorted(past_grouped.items(), key=lambda x: x[0], reverse=True)
        ]

        current_app.logger.info(
            "Rendering route_overview.html with next_pickup=%s, #upcoming=%d, #past=%d",
            next_pickup['date'] if next_pickup else None,
            len(remaining_upcoming),
            len(past_dates_final)
        )

        return render_template(
            "admin/route_overview.html",
            next_pickup=next_pickup,
            upcoming_dates=remaining_upcoming,
            past_dates=past_dates_final
        )

    

    @app.route('/view-route-info')
    @login_required
    def view_route_info():
        selected_date = request.args.get('date')
        current_app.logger.info("GET /view-route-info - user requested route info for date=%s", selected_date)

        if not selected_date:
            current_app.logger.warning("No 'date' parameter provided to /view-route-info.")

            return "Date parameter is required", 400

        formatted_date = format_date(selected_date)

        # Query "Requested" pickups
        all_pickups = PickupRequest.query.filter_by(
            request_date=selected_date,
        ).all()
        current_app.logger.debug("Found %d 'Requested' pickups for date=%s", len(all_pickups), selected_date)


        requested_addresses = [p.address + ", " + p.city + " CA" for p in all_pickups]

        # Now call our route-optimization function
        admin_cfg = DBConfig.query.filter_by(key='admin_address').first()
        depot     = admin_cfg.value

        try:
            sorted_addresses, total_time_seconds, leg_times = compute_optimized_route(
                requested_addresses,
                start_location=depot,           # identical start/end rules as live view
                end_location=depot,
                api_key=os.environ.get("GOOGLE_BACKEND_API_KEY")
            )
        except Exception:
            current_app.logger.exception("Distance-matrix/TSP error")
            sorted_addresses, total_time_seconds, leg_times = requested_addresses, 0, []

        total_time_str = seconds_to_pretty(total_time_seconds)

        return render_template(
            'admin/view_route_info.html',
            date=formatted_date,
            all_pickups = all_pickups,
            total_time_str = total_time_str,
        )
    
    def _clean_coord(s: str | None) -> str | None:
        """Tidy a 'lon,lat' string – Mapbox accepts it w/ no spaces."""
        if s and _coords_like(s):
            return s.replace(" ", "")
        return s

    def _pickup_addr(pr) -> str:
        """
        Return either the geocode 'lon,lat' (preferred) or a
        plain‑text address for a PickupRequest row.
        """
        geo = _clean_coord(getattr(pr, "geocoded_addr", None))
        if geo:
            return geo
        # Fallback – tweak to match how you normally format text addresses
        return f"{pr.address}, {pr.city}, CA {pr.zipcode}"
    
    @app.route('/live-route', methods=['GET'])
    @login_required
    def live_route():
        """
        Serve the live route.
        Re‑optimise only if:
        • the cache is >15 min old, or
        • RouteSolution.needs_refresh is True.
        """
        current_app.logger.info("GET /live-route")

        CACHE_MAX_AGE_MINUTES = 15
        pickup_status_form    = PickupStatusForm()
        selected_date         = request.args.get('date')
        if not selected_date:
            return "Date parameter is required", 400

        # ------------------------------------------------------------------ #
        # 1) Build today's waypoint list
        # ------------------------------------------------------------------ #
        pickups_requested = PickupRequest.query.filter_by(
            request_date=selected_date, status='Requested'
        ).all()

        driver_loc = DriverLocation.query.first()
        if driver_loc and driver_loc.full_address():
            driver_current_location = _clean_coord(driver_loc.full_address())
        else:
            admin_cfg = DBConfig.query.filter_by(key='geocoded_admin_addr').first()
            driver_current_location = _clean_coord(
                admin_cfg.value if admin_cfg else "5389 Mallard Dr., Pleasanton, CA 94566"
            )

        depot_cfg = DBConfig.query.filter_by(key='geocoded_admin_addr').first()
        depot_address = _clean_coord(
            depot_cfg.value if depot_cfg else "5389 Mallard Dr., Pleasanton, CA 94566"
        )

        addresses = [driver_current_location] + [_pickup_addr(p) for p in pickups_requested] + [depot_address]

        # ------------------------------------------------------------------ #
        # 2) Cache handling
        # ------------------------------------------------------------------ #
        cached = RouteSolution.query.filter_by(date=selected_date).first()
        should_refresh = cached is None
        display_str    = ""

        if cached:
            age = datetime.now() - cached.last_updated
            if age >= timedelta(minutes=CACHE_MAX_AGE_MINUTES) or cached.needs_refresh:
                should_refresh = True
                cached.needs_refresh = False      # we'll satisfy it right now
            else:
                old_route = json.loads(cached.route_json)
                old_legs  = json.loads(cached.legs_json or "[]")

                # Peel off already‑visited legs (difference in list lengths)
                removed_count = max(0, len(old_route) - len(addresses))
                travelled_sec = 0
                for _ in range(removed_count):
                    if len(old_route) > 2:
                        travelled_sec += old_legs.pop(0)
                        old_route.pop(1)

                old_route[0] = driver_current_location
                remaining_sec = max(0, hms_to_seconds(cached.total_time_str) - travelled_sec)

                cached.route_json     = json.dumps(old_route)
                cached.legs_json      = json.dumps(old_legs)
                cached.total_time_str = seconds_to_hms(remaining_sec)
                cached.last_updated   = datetime.now()
                db.session.commit()

                addresses     = old_route
                display_str   = seconds_to_pretty(remaining_sec)

        # ------------------------------------------------------------------ #
        # 3) Re‑optimise if required
        # ------------------------------------------------------------------ #
        if should_refresh:
            final_route, total_seconds, legs_seconds = compute_optimized_route(
                waypoints=addresses[1:-1],
                start_location=addresses[0],
                end_location=addresses[-1],
            )

            if cached:
                cached.route_json     = json.dumps(final_route)
                cached.legs_json      = json.dumps(legs_seconds)
                cached.total_time_str = seconds_to_hms(total_seconds)
                cached.last_updated   = datetime.now()
            else:
                cached = RouteSolution(
                    date=selected_date,
                    route_json=json.dumps(final_route),
                    legs_json=json.dumps(legs_seconds),
                    total_time_str=seconds_to_hms(total_seconds),
                    last_updated=datetime.now(),
                    needs_refresh=False,
                )
                db.session.add(cached)

            db.session.commit()
            addresses   = final_route
            display_str = seconds_to_pretty(total_seconds)

        # ------------------------------------------------------------------ #
        # 4) Sort pickups by live route order
        # ------------------------------------------------------------------ #
        route_map = {addr: idx for idx, addr in enumerate(addresses)}
        pickups_requested.sort(
            key=lambda pr: route_map.get(f"{pr.address}, {pr.city} CA", 999_999)
        )

        pickups_completed = PickupRequest.query.filter(
            PickupRequest.request_date == selected_date,
            or_(PickupRequest.status == 'Complete', PickupRequest.status == 'Incomplete')
        ).all()

        return render_template(
            "admin/live_route.html",
            date=format_iso_to_pretty(selected_date),
            pickups_requested=pickups_requested,
            pickups_completed=pickups_completed,
            route=addresses,
            pickup_status_form=pickup_status_form,
            total_time_str=display_str,
        )



    @app.route('/toggle_pickup_status', methods=['POST'])
    @login_required
    def toggle_pickup_status():
        """
        Toggle between 'Requested' and 'Complete'/'Incomplete' for a pickup.
        • When a stop is *added back* to the route (→ 'Requested') mark
        the day's RouteSolution as needing a refresh.
        • When a stop is *removed* (→ 'Complete' or 'Incomplete') keep the
        cached route and just move the driver location forward.
        """
        current_app.logger.info("POST /toggle_pickup_status - Toggle pickup status initiated.")
        form = PickupStatusForm()

        if not form.validate_on_submit():
            current_app.logger.warning("Form validation failed: %s", form.errors)
            return "Error: Form validation failed", 400

        pickup_id = form.pickup_id.data
        pickup    = db.session.get(PickupRequest, pickup_id)

        if not pickup:
            current_app.logger.warning("Pickup not found: %s", pickup_id)
            return "Error: Pickup not found", 404

        old_status = pickup.status
        current_app.logger.info("Current pickup status for %s is '%s'", pickup_id, old_status)

        # ------------------------------------------------------------------ #
        # 1) Flip the status
        # ------------------------------------------------------------------ #
        if old_status in ("Complete", "Incomplete"):
            new_status = "Requested"
            pickup.status = new_status
            pickup.pickup_complete_info = None
        else:
            new_status = "Complete"
            pickup.status = new_status
            pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()
            update_driver_location(pickup.address, pickup.city)

        # ------------------------------------------------------------------ #
        # 2) Flag the route cache intelligently
        # ------------------------------------------------------------------ #
        cached = RouteSolution.query.filter_by(date=pickup.request_date).first()
        if cached:
            cached.needs_refresh = (new_status == "Requested")  # True = added stop

        db.session.commit()
        current_app.logger.info("Pickup %s toggled to '%s'", pickup_id, new_status)

        return jsonify({"message": "Status updated successfully", "new_status": new_status})



    @app.route('/mark-pickup-not-possible', methods=['POST'])
    @login_required
    def mark_pickup_not_possible():
        """
        Mark a pickup as 'Incomplete' (cannot be done today).
        Does NOT invalidate the cache (it only removes a stop).
        """
        current_app.logger.info("POST /mark-pickup-not-possible")
        form = PickupStatusForm()

        if not form.validate_on_submit():
            current_app.logger.warning("Form validation failed: %s", form.errors)
            return "Error: Form validation failed", 400

        pickup_id = form.pickup_id.data
        pickup    = db.session.get(PickupRequest, pickup_id)

        if not pickup:
            current_app.logger.warning("Pickup not found: %s", pickup_id)
            return "Error: Pickup not found", 404

        pickup.status = "Incomplete"
        pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()

        cached = RouteSolution.query.filter_by(date=pickup.request_date).first()
        if cached:
            cached.needs_refresh = False   # removing a stop never forces a reroute

        db.session.commit()
        current_app.logger.info("Pickup %s marked 'Incomplete'.", pickup_id)

        return jsonify({"message": "Status updated successfully", "new_status": pickup.status})


    def update_driver_location(address, city):
        """
        Update the driver's location to the provided address/city.
        If no DriverLocation row exists yet, create one.
        """
        current_app.logger.info("Pickup complete, updating driver location.")

        driver_loc = DriverLocation.query.first()
        if not driver_loc:
            current_app.logger.debug("No existing DriverLocation found. Creating a new record.")

            driver_loc = DriverLocation(address=address, city=city)
            db.session.add(driver_loc)
        else:
            current_app.logger.debug("Existing DriverLocation found. Updating record.")

            driver_loc.address = address
            driver_loc.city = city

        db.session.commit()
        current_app.logger.info("Driver location updated successfully.")

    @app.route('/contact-form-entry', methods=['POST'])
    @limiter.limit("10 per hour")
    def contact_form_entry():
        form = ContactForm()
        if form.validate_on_submit():
            name    = form.name.data
            email   = form.email.data
            message = form.message.data

            current_app.logger.info(
                "Contact form validated."
            )

            #sent = send_contact_email(name, email, message)
            sent = True
            if sent:
                current_app.logger.info("Contact email sent successfully.")
                return jsonify(valid=True,  reason=""), 200
            else:
                current_app.logger.warning("Contact email failed to send.")
                return jsonify(valid=False, reason="Email sending failed."), 500

        # validation failed
        current_app.logger.warning("Contact form invalid: %s", form.errors)
        # flatten the first error from each field
        messages = []
        for field, errs in form.errors.items():
            messages += errs
        return jsonify(valid=False, reason=" ".join(messages)), 400



    # --------------------------------------------------

    # ERROR HANDLING AND ENDPOINTS
    
    # --------------------------------------------------

    @app.errorhandler(429)
    def too_many_requests(e):
        # First generate the default RateLimitExceeded response so we can read its headers'
        current_app.logger.info("Rate limiter hit, redirecting user.")

        default_resp = e.get_response()
        retry_after = default_resp.headers.get("Retry-After", None)

        # Default fallback text
        pretty = "an hour"
        if retry_after and retry_after.isdigit():
            seconds = int(retry_after)
            if seconds >= 3600 and seconds % 3600 == 0:
                hours = seconds // 3600
                pretty = f"{hours} hour" + ("s" if hours != 1 else "")
            elif seconds >= 60 and seconds % 60 == 0:
                minutes = seconds // 60
                pretty = f"{minutes} minute" + ("s" if minutes != 1 else "")
            else:
                pretty = f"{seconds} second" + ("s" if seconds != 1 else "")
        # Render our custom template, passing the human‑friendly string
        return make_response(
            render_template("429.html", retry_after=pretty),
            429,
            default_resp.headers  # preserves Retry‑After, RateLimit headers, etc.
        )



    @app.errorhandler(404)
    def handle_404(e):
        """
        Handle 'page not found' errors. We email the error details, then
        redirect the user to the /error page.
        """
        current_app.logger.warning(f"404 Not Found: {request.path}")
        record_404()
        if request.path.startswith('/.well-known/'):
            return '', 204
        return redirect(url_for('error'))
    
    @app.errorhandler(500)
    def handle_500(e):
        current_app.logger.error("500 error occurred.")
        record_5xx
        return redirect(url_for('error'))

    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Handle any other uncaught exceptions (including 500 errors).
        We email the error details, then redirect the user to /error.
        """
        current_app.logger.exception("Unhandled exception occurred.")
        return redirect(url_for('error'))

    @app.route('/error')
    def error():
        return render_template('error.html')

    # --------------------------------------------------

    # DB FUNCTIONS
    
    # --------------------------------------------------

    @app.cli.command('reset-db')
    def reset_db():
        """Drops all tables and recreates them."""
        with app.app_context():
            print("Dropping all tables...")
            db.drop_all()
            print("Creating all tables...")
            db.create_all()
            print("Database reset complete.")

    backfill_mod.register(app)

    return app

def seed_schedule_if_necessary():
    """
    If the ServiceSchedule table is empty, seed it with Monday-Sunday defaults.
    """
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    existing_count = ServiceSchedule.query.count()
    if existing_count == 0:
        for day in days:
            record = ServiceSchedule(day_of_week=day, is_available=False,
                                     slot1_start=None, slot1_end=None,
                                     slot2_start=None, slot2_end=None)
            db.session.add(record)
        db.session.commit()

if __name__ == '__main__':
    app = create_app()
    app.run(host="localhost", port=3000, debug=True)
