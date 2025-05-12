# app.py
from flask import Flask, request, render_template, redirect, url_for, jsonify, make_response, session, current_app, flash, abort
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler
from models import db, PickupRequest, ServiceSchedule, DriverLocation, RouteSolution, Config as DBConfig, add_request, get_service_schedule, get_address
from config import Config
from extensions import mail
import requests
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt, JsonWebKey 
from dotenv import load_dotenv
from helpers.address import verifyZip
from helpers.contact import submitContact
from helpers.helpers import format_date
from helpers.routing_old import get_optimized_route
from helpers.scheduling import build_schedule
from helpers.emailer import send_contact_email, send_request_email, send_error_report, send_editted_request_email
from helpers.routing import fetch_distance_matrix, solve_tsp, seconds_to_hms
from helpers.forms import RequestForm, DateSelectionForm, UpdateAddressForm, PickupStatusForm, AdminScheduleForm, AdminAddressForm, ScheduleDayForm, DateRangeForm, EditRequestTimeForm, CancelEditForm, CancelRequestForm, EditRequestInitForm, DeletePickupForm, ContactForm
from datetime import date, timedelta, datetime
from sqlalchemy import func
from sqlalchemy import or_
from pycognito import Cognito
from functools import wraps
from werkzeug.utils import secure_filename
import os
import csv
import io
import json
from urllib.parse import urlencode
import uuid

csrf = CSRFProtect()

import traceback

limiter = Limiter(key_func=get_remote_address, default_limits=["100 per hour"])

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    oauth = OAuth(app)

    COGNITO_DOMAIN        = os.environ["COGNITO_DOMAIN"]           # e.g.  demo-domain.auth.us-east-2.amazoncognito.com
    COGNITO_CLIENT_ID     = os.environ["COGNITO_CLIENT_ID"]

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

    # if you have a Redis instance:
    # limiter = Limiter(
    #     key_func=get_remote_address,
    #     storage_uri="redis://localhost:6379"
    # )

    # for simple in‑memory (not recommended for prod):
    limiter.init_app(app)


    app.config['SESSION_COOKIE_HTTPONLY'] = True
    #app.config['SESSION_COOKIE_SECURE'] = True # Must be true for production
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' 
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 5 MB

    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

    mail.init_app(app)
    csrf.init_app(app)


    # 4) Initialize your extensions
    db.init_app(app)
    print("App initialized.")

    from flask_migrate import Migrate
    migrate = Migrate(app, db)

    # 5) Create tables once if needed
    with app.app_context():
        #db.drop_all() #to reset the db
        db.create_all()
        seed_schedule_if_necessary()

    @app.context_processor
    def inject_contact_form():
        # Every template now has `contact_form` in its context
        return { 'contact_form': ContactForm() }

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)
        return decorated_function
    
    if not app.debug and not app.testing:
        # Production: Use rotating file logs
        file_handler = RotatingFileHandler("app.log", maxBytes=102400, backupCount=5)
        file_handler.setLevel(app.config['LOGGER_LEVEL'])
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        )
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)

    # For local dev, or if you want DEBUG info:
    app.logger.setLevel(app.config['LOGGER_LEVEL'])


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
    


    # --------------------------------------------------

    # START REQUEST FLOW

    # --------------------------------------------------




    @app.route('/request_pickup')
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
        
        current_app.logger.info(
            "Recaptcha site key = %r, secret key = %r",
            current_app.config.get('RECAPTCHA_PUBLIC_KEY'),
            current_app.config.get('RECAPTCHA_PRIVATE_KEY'),
        )
        return render_template('request.html', zipcode = zipcode, city=city, form=form)


    @app.route('/request_init', methods=['GET', 'POST'])
    @limiter.limit("5 per hour")
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
            city    = form.city.data
            zip_    = form.zip.data
            notes   = form.notes.data

            gated = form.gated.data
            selected_gated_option = form.selectedGatedOption.data  # or form.gatedOptions.data if that fits your logic
            gate_code = form.finalGateCode.data or None
            notify_val = form.finalNotice.data
            notify = True if notify_val == 'true' else False
            current_app.logger.debug("New request created.")

            # Handle file upload
            qr_code_file = form.qrCodeInput.data
            qr_code_filename = None
            if qr_code_file:
                folder_path = 'static/images/qr_codes'
                os.makedirs(folder_path, exist_ok=True)
                filename = secure_filename(qr_code_file.filename)
                qr_code_file.save(os.path.join(folder_path, filename))
                qr_code_filename = filename
                current_app.logger.info("QR code file uploaded: %s", qr_code_filename)

            print("New request created, unfinished.")
            
            # Insert into DB (assuming add_request is defined elsewhere)
            new_id = add_request(
                fname=fname,
                lname=lname,
                email=email,
                phone_number=phone,
                address=address,
                city=city,
                zipcode=zip_,
                notes=notes,
                gated=gated,
                qr_code=qr_code_filename,
                gate_code=gate_code,
                notify=notify,
                status="Unfinished"
            )
            pickup = db.session.get(PickupRequest, new_id)
            pickup_code= pickup.request_id
            current_app.logger.info("New pickup request created.")
            return redirect(url_for('select_date', request_id=pickup_code))
        
        if request.method == 'POST':
            current_app.logger.warning("POST /request_init - Form validation failed. Errors: %s", form.errors)

        current_app.logger.info("GET /request_init - Rendering request form.")
        return render_template('request.html', form=form)


    @app.route('/date', methods=['GET', 'POST'])
    def select_date():
        request_id = request.args.get('request_id')
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
        current_app.logger.debug("Built schedule for offset=%d. base_date_str=%s, days_list=%s",
                             offset, base_date_str, days_list)
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

            if session.get('confirmation_email_sent'):
                current_app.logger.info("Sending edited pickup request email for request_id=%s", request_id)
                send_editted_request_email(pickup)
                current_app.logger.debug("Edited pickup request email sent for request_id=%s", request_id)
            else:
                current_app.logger.info("Confirmation email not yet sent for request_id=%s, sending to confirmation page", request_id)

            return redirect(url_for('confirmation', request_id=request_id))
        
        current_app.logger.info(
            "User is selecting a date/time for request_id=%s, offset=%d. Rendering select_date.html.",
            request_id, offset
        )

        print("User selecting a date.")
        return render_template('select_date.html',
                            form=form,
                            pickup=pickup,
                            days_list=days_list,
                            offset=offset,
                            max_offset=2,
                            request_id=request_id,
                            base_date_str=base_date_str)
    
    @app.route('/confirmation')
    def confirmation():    
        request_id = request.args.get('request_id')
        current_app.logger.debug("confirmation route accessed with request_id=%s", request_id)

        # Verify the request ID exists in the session and matches
        if 'pickup_request_id' not in session or session['pickup_request_id'] != request_id:
            current_app.logger.warning("Unauthorized access attempt with request_id=%s", request_id)
            abort(404)

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

        update_address_form = UpdateAddressForm(obj=pickup)
        # In your confirmation route
        update_address_form.request_id.data = pickup.request_id
        update_address_form.address.data = pickup.address
        update_address_form.city.data    = pickup.city
        update_address_form.zipcode.data = pickup.zipcode
        update_address_form.page.data    = "confirmation"

        current_app.logger.info("Rendering confirmation.html for request_id=%s", request_id)

        return render_template('confirmation.html', pickup=pickup, request_id=pickup.request_id, form=update_address_form)


    @app.route('/update_address', methods=['POST'])
    def update_address():
        form = UpdateAddressForm()
        if form.validate_on_submit():
            # Retrieve validated data from the form
            request_id = form.request_id.data
            address    = form.address.data
            city       = form.city.data
            zip_code   = form.zipcode.data
            page       = form.page.data

            current_app.logger.info("Received valid POST to update address for request_id=%s", request_id)

            # Fetch the pickup request from the database
            pickup = PickupRequest.query.filter_by(request_id=request_id).first()

            if not pickup:
                current_app.logger.warning("No PickupRequest found for request_id=%s", request_id)
                return jsonify({
                    "status": "error",
                    "message": f"No record found for request_id={request_id}"
                }), 400

            # Update the fields
            pickup.address = address
            pickup.city    = city
            pickup.zipcode = zip_code

            # Commit changes to the database
            db.session.commit()
            current_app.logger.info(
                "Successfully updated address for request_id=%s",
                request_id
            )

            # Redirect based on the page value
            if page == "edit_request":
                current_app.logger.debug("Sending edited request email for request_id=%s", request_id)
                send_editted_request_email(pickup)
                current_app.logger.debug("Edited request email sent for request_id=%s", request_id)

                return redirect(url_for('edit_request', request_id=request_id))
            else:
                current_app.logger.debug("Sending edited request email for request_id=%s", request_id)
                send_editted_request_email(pickup)
                current_app.logger.debug("Edited request email sent for request_id=%s", request_id)
                session['pickup_request_id'] = request_id
                return redirect(url_for('confirmation', request_id=request_id))
        else:
            current_app.logger.warning(
                "Form validation failed for update_address. Errors: %s", form.errors
            )
            return jsonify({
                "status": "error",
                "message": "Invalid form submission."
            }), 400



    # --------------------------------------------------

    # START EDIT REQUEST FLOW

    # --------------------------------------------------



    @app.route('/edit-request-init', methods=['GET'])
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
        # 1) basic format
        if not request_id.isdigit() or len(request_id) != 6:
            return False, (
                "Your code must be exactly 6 digits and contain only numbers. "
                "Please check and try again."
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
                "The code and e-mail do not match. Please verify and try again."
            )

        # 3) date in the past?
        if pickup.request_date:
            try:
                if datetime.strptime(pickup.request_date, '%Y-%m-%d').date() < datetime.now().date():
                    return False, (
                        "That request date has already passed and can’t be edited."
                    )
            except ValueError:
                current_app.logger.error("Bad date on request %s", request_id)
                return False, (
                    "We couldn’t verify the request date. Please contact us."
                )

        # 4) status checks
        if pickup.status in ("Cancelled", "Completed"):
            return False, f"Your request has been {pickup.status.lower()} and cannot be edited."

        return True, pickup
    
    @app.route('/edit-request', methods=['POST'])
    def edit_request():
        """Receives the code+email form, validates via can_edit(), and
        either shows the edit screen or bounces back with a flash alert."""
        current_app.logger.info("POST /edit-request - User accessing the edit request page.")

        form = EditRequestInitForm()

        if not form.validate_on_submit():
            flash('Invalid form submission.', 'danger')
            current_app.logger.warning("Invalid form submission at edit_request")
            return redirect(url_for('edit_request_init'))

        ok, result = can_edit(form.request_id.data, form.requester_email.data)
        if not ok:
            current_app.logger.warning("edit_request endpoint hit, email and request ID don't match. Request ID = %s", form.request_id.data)
            flash(result, 'warning')
            return redirect(url_for('edit_request_init'))

        # ── All checks passed ────────────────────────────────────────────
        current_app.logger.info("Request to edit valid, rendering page.")

        pickup = result

        update_form = UpdateAddressForm(obj=pickup)
        update_form.request_id.data = pickup.request_id
        update_form.page.data = "edit_request"

        cancel_form = CancelRequestForm()
        cancel_form.request_id.data = pickup.request_id

        return render_template(
            'edit_request.html',
            partial="/partials/_editRequest_info.html",
            pickup=pickup,
            max_offset=2,
            request_id=pickup.request_id,
            form=update_form,
            cancel_form=cancel_form,
        )
        
    @app.route('/edit-request-time', methods=['GET'])
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
            "Built schedule for offset=%d (base_date_str=%s). Days list: %s",
            offset, base_date_str, days_list
        )

        update_address_form = UpdateAddressForm(obj=pickup)

        cancel_form = CancelRequestForm()
        cancel_form.request_id.data = pickup.request_id

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
                            cancel_form=cancel_form)
    
    @app.route('/edit-request-time-submit', methods=['POST'])
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

            send_editted_request_email(pickup)

            return redirect(url_for('edit_request', request_id=request_id))
        else:
            current_app.logger.warning("Form validation failed for edit-request-time-submit. Errors: %s", form.errors)
            # Optionally log or flash the errors from form.errors here for debugging
            return redirect(url_for('edit_request'))


    
    @app.route('/verify_zip', methods=['GET'])
    def verify_zip():
        current_app.logger.debug("GET /verify_zip - verifying user zip.")

        zip_code = request.args.get('zipcode')
        current_app.logger.debug("Zip code provided: %s", zip_code)

        approved_zips = ["94566", "94568", "94588", "94568", "94550", "94551"] 
        result = verifyZip(approved_zips, zip_code)
        current_app.logger.debug("verifyZip result: %s", result)

        return jsonify(result)
    
    @app.route('/cancel-request', methods=["POST"])
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
                return jsonify({
                    "valid": True,
                    "reason": "Request cancelled."
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
    def admin_login():
        """Kick off OIDC flow."""
        redirect_uri = url_for("callback", _external=True)  # HTTPS in prod
        #redirect_uri = url_for("callback", _external=True, _scheme="https")  # HTTPS in prod
        current_app.logger.debug("Redirecting admin to Cognito login: %s", redirect_uri)
        return oauth.oidc.authorize_redirect(redirect_uri)
    
    @app.route("/callback")
    def callback():
        """Cognito redirects back here with ?code= ; exchange it for tokens."""
        current_app.logger.info("GET /callback – exchanging code for tokens")

        token = oauth.oidc.authorize_access_token()  # state + PKCE automatically verified
        current_app.logger.debug("Token payload (sans id_token): %s",
                                {k: v for k, v in token.items() if k != "id_token"})

        # --------------------------------------------------------------------------
        # Extra defence: verify the ID-token signature & claims ourselves :contentReference[oaicite:1]{index=1}
        # --------------------------------------------------------------------------
        try:
            jwks_uri = oauth.oidc.load_server_metadata()["jwks_uri"]
            jwks     = JsonWebKey.import_key_set(requests.get(jwks_uri, timeout=5).json())
            id_token = jwt.decode(token["id_token"], jwks)  # verifies signature
            id_token.validate()                            # exp, iat, aud, iss…
        except Exception as exc:
            current_app.logger.exception("ID-token validation failed: %s", exc)
            return "Invalid id_token", 400

        # Persist only what you really need
        session.permanent = True
        session["user"]   = {"sub": id_token["sub"], "email": id_token.get("email")}
        session['logged_in'] = True
        current_app.logger.info("Admin %s logged in", id_token.get("email"))

        return redirect(url_for("admin_console"))


    @app.route("/admin/logout")
    def admin_logout():
        """Clear local session *and* hit Cognito’s global-sign-out endpoint."""
        session.clear()
        logout_uri   = url_for("/", _external=True, _scheme="https")
        cognito_url  = (f"https://{COGNITO_DOMAIN}/logout"
                        f"?client_id={COGNITO_CLIENT_ID}&logout_uri={logout_uri}")
        return redirect(cognito_url)
        
    @app.route('/admin-console', methods=['GET', 'POST'])
    @login_required
    def admin_console():
        current_app.logger.info("Accessing /admin-console.")

        today = datetime.today().date()
        # Default to the current week: from Monday to today.
        start_of_week = today - timedelta(days=today.weekday())
        default_start_date = start_of_week
        default_end_date = today

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
            current_app.logger.debug("Using default date range for admin_console: %s to %s", start_date, end_date)

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
            PickupRequest.request_date >= start_date.strftime("%Y-%m-%d"),
            PickupRequest.request_date <= end_date.strftime("%Y-%m-%d")
        ).count()

        current_app.logger.debug(
            "Computed daily_counts=%s, pickups_total=%d for date range %s - %s",
            daily_counts, pickups_total, start_date, end_date
        )

        return render_template(
            'admin/admin_console.html',
            daily_counts=daily_counts,
            pickups_this_week=pickups_total,
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
            elif admin_address_form.submit.data and admin_address_form.validate_on_submit():
                # Process address update
                new_address = admin_address_form.admin_address.data
                current_app.logger.info("AdminAddressForm was submitted and validated. New address=%s", new_address)

                config = DBConfig.query.filter_by(key='admin_address').first()
                if config:
                    old_address_val = config.value
                    config.value = new_address
                    current_app.logger.debug("Updated admin_address from '%s' to '%s'.", old_address_val, new_address)
                else:
                    config = DBConfig(key='admin_address', value=new_address)
                    db.session.add(config)
                    current_app.logger.debug("Created new admin_address config entry: '%s'.", new_address)
                
                db.session.commit()
                current_app.logger.info("Address updated; redirecting to /admin-schedule.")

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
        if form.validate_on_submit():
            new_address = form.admin_address.data
            current_app.logger.debug("Form validated. New address value: %s", new_address)

            config = DBConfig.query.filter_by(key='admin_address').first()
            if config:
                old_address = config.value
                config.value = new_address
                current_app.logger.debug("Updated existing admin_address from '%s' to '%s'.", old_address, new_address)
            else:
                config = DBConfig(key='admin_address', value=new_address)
                db.session.add(config)
                current_app.logger.debug("Created new DBConfig entry for admin_address: '%s'.", new_address)
            
            db.session.commit()
            current_app.logger.info("Admin address updated. Redirecting to admin_schedule.")
            return redirect(url_for('admin_schedule'))
        else:
            current_app.logger.warning("Form validation failed in admin_set_address. Errors: %s", form.errors)
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
        sort_by = request.args.get('sort_by')
        if sort_by == 'date_filed':
            current_app.logger.debug("Sorting pickups by date_filed desc.")
            query = query.order_by(PickupRequest.date_filed.desc())
        elif sort_by == 'date_requested':
            current_app.logger.debug("Sorting pickups by request_date desc.")
            query = query.order_by(PickupRequest.request_date.desc())
        else:
            current_app.logger.debug("Using default sorting by ID desc.")
            query = query.order_by(PickupRequest.id.desc())

        requests = query.all()
        current_app.logger.debug("Found %d pickup requests after applying filters/sorts.", len(requests))


        return render_template('admin/admin_pickups.html', schedule_data=schedule_data, requests=requests, delete_form=delete_form)

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


    @app.route('/admin/download_csv')
    @login_required
    def download_csv():
        current_app.logger.info("GET /admin/download_csv - Admin downloading CSV of all pickup requests.")

        # Query all pickup requests
        pickup_requests = PickupRequest.query.all()
        current_app.logger.debug("Fetched %d pickup requests to include in CSV.", len(pickup_requests))

        # Create an in-memory CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header with all fields
        writer.writerow([
            "ID", "First Name", "Last Name", "Email", "Phone Number",
            "Address", "City", "Zipcode", "Notes", "Status",
            "Gated", "QR Code", "Gate Code", "Notify",
            "Request Date", "Request Time", "Date Filed",
            "Pickup Complete Info", "Request ID"
        ])

        # Write rows for each pickup request
        for req in pickup_requests:
            writer.writerow([
                req.id, req.fname, req.lname, req.email, req.phone_number,
                req.address, req.city, req.zipcode, req.notes, req.status,
                req.gated, req.qr_code, req.gate_code, req.notify,
                req.request_date, req.request_time, req.date_filed,
                req.pickup_complete_info, req.request_id
            ])

        # Make a Flask response with the CSV data
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=pickup_requests.csv"
        response.headers["Content-type"] = "text/csv"

        current_app.logger.info("CSV created and sent to client.")

        return response
        


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
            if date_str not in upcoming_grouped:
                upcoming_grouped[date_str] = []
            upcoming_grouped[date_str].append({
                'timeframe': row.request_time,
                'count': row.pickup_count
            })

        current_app.logger.debug("Upcoming grouped pickups: %s", upcoming_grouped)
            
        # Sort upcoming dates ascending.
        upcoming_dates_sorted = sorted(upcoming_grouped.items(), key=lambda x: x[0])
        
        # Separate out the earliest upcoming date as "next_pickup".
        if upcoming_dates_sorted:
            next_date, next_timeframes = upcoming_dates_sorted[0]
            next_pickup = {
                'date': next_date,
                'formatted_date': format_date(next_date),
                'timeframes': next_timeframes
            }
            remaining_upcoming = []
            for date_str, timeframes in upcoming_dates_sorted[1:]:
                remaining_upcoming.append({
                    'date': date_str,
                    'formatted_date': format_date(date_str),
                    'timeframes': timeframes
                })
            current_app.logger.debug("Next pickup date=%s, remaining upcoming count=%d", next_date, len(remaining_upcoming))

        else:
            next_pickup = None
            remaining_upcoming = []
            current_app.logger.debug("No upcoming dates found.")

        
        # --- Past Pickups ---
        # Query past pickups grouped by date and timeframe.
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
            if date_str not in past_grouped:
                past_grouped[date_str] = []
            past_grouped[date_str].append({
                'timeframe': row.request_time,
                'count': row.pickup_count
            })
        current_app.logger.debug("Past grouped pickups: %s", past_grouped)
        
        # Sort past dates descending.
        past_dates_sorted = sorted(past_grouped.items(), key=lambda x: x[0], reverse=True)
        past_dates_final = []
        for date_str, timeframes in past_dates_sorted:
            past_dates_final.append({
                'date': date_str,
                'formatted_date': format_date(date_str),
                'timeframes': timeframes
            })
        current_app.logger.info("Rendering route_overview.html with next_pickup=%s, #upcoming=%d, #past=%d",
                            next_pickup['date'] if next_pickup else None,
                            len(remaining_upcoming), len(past_dates_final))
        
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
        adminAddress = DBConfig.query.filter_by(key='admin_address').first()
        current_app.logger.debug("Using start_location='%s' for get_optimized_route.", adminAddress)

        try:
            sorted_addresses, total_time_seconds, leg_times = get_optimized_route(
                addresses=requested_addresses,
                # Optional: provide start_location if you have a depot location
                start_location=adminAddress.value,
                api_key=os.environ.get("GOOGLE_MAPS_API_KEY")
            )
            current_app.logger.debug("Route optimization success. Total time (sec)=%d", total_time_seconds)

        except Exception as e:
            current_app.logger.exception("Distance matrix error during view_route_info for date=%s:", selected_date)

            sorted_addresses = requested_addresses
            total_time_seconds = 0
            leg_times = []

        def sort_key(pr):
            full_addr = pr.address + ", " + pr.city + " CA"
            try:
                return sorted_addresses.index(full_addr)
            except ValueError:
                return 999999

        all_pickups.sort(key=sort_key)

        def seconds_to_hms(sec):
            hours = sec // 3600
            mins = (sec % 3600) // 60
            if hours > 0:
                return f"{hours} hr {mins} min"
            else:
                return f"{mins} min"

        total_time_str = seconds_to_hms(total_time_seconds)
        current_app.logger.info("view_route_info final route computed. Rendering view_route_info.html")


        return render_template(
            'admin/view_route_info.html',
            date=formatted_date,
            all_pickups = all_pickups,
            total_time_str = total_time_str,
        )
    
    @app.route('/live-route', methods=['GET'])
    @login_required
    def live_route():
        current_app.logger.info("GET /live-route - showing live route info.")

        CACHE_MAX_AGE_MINUTES = 10
        pickup_status_form = PickupStatusForm()
        selected_date = request.args.get('date')
        if not selected_date:
            current_app.logger.warning("No 'date' provided for /live-route.")
            return "Date parameter is required", 400
        
        # 1) Get pickups
        current_app.logger.debug("Loading pickups for date=%s with status='Requested'.", selected_date)

        pickups_requested = PickupRequest.query.filter_by(
            request_date=selected_date,
            status='Requested'
        ).all()

        # 2) Driver location or fallback
        driver_loc = DriverLocation.query.first()
        if driver_loc and driver_loc.full_address():
            driver_current_location = driver_loc.full_address()
            current_app.logger.debug("Using driver's current location: %s", driver_current_location)

        else:
            admin_config = DBConfig.query.filter_by(key='admin_address').first()
            driver_current_location = admin_config.value if admin_config else "5831 Mallard Dr., Pleasanton CA"
            current_app.logger.debug("No valid driver location, falling back to admin address: %s", driver_current_location)


        # 3) Always end at admin location
        final_admin_config = DBConfig.query.filter_by(key='admin_address').first()
        final_admin_address = final_admin_config.value if final_admin_config else "5831 Mallard Dr., Pleasanton CA"

        addresses = [driver_current_location]
        for p in pickups_requested:
            addresses.append(f"{p.address}, {p.city} CA")
        addresses.append(final_admin_address)  # this is n-1

        current_app.logger.debug("Compiled addresses for route: %s", addresses)

        
        # 5) Check cache for 'selected_date'
        cached_solution = RouteSolution.query.filter_by(date=selected_date).first()
        should_refresh = True

        if cached_solution:
            age = datetime.now() - cached_solution.last_updated
            current_app.logger.debug("Cached route solution found for date=%s; age=%s", selected_date, age)

            if age < timedelta(minutes=CACHE_MAX_AGE_MINUTES):
                # Compare route size and start/end
                cached_route_list = json.loads(cached_solution.route_json)

                # Quick checks:
                same_size = (len(cached_route_list) == len(addresses))
                same_start = (cached_route_list[0] == driver_current_location)
                same_end = (cached_route_list[-1] == final_admin_address)
                if same_size and same_start and same_end:
                    current_app.logger.debug("Cache is still valid (size/start/end match). Using cached route.")
                    should_refresh = False

        # 6) Either use the cached route or recalc
        if should_refresh:
            current_app.logger.debug("Recomputing route for date=%s, addresses=%s", selected_date, addresses)

            print("Recomputing route for", addresses)
            try:
                matrix = fetch_distance_matrix(addresses)
            except Exception as e:
                current_app.logger.exception("Distance matrix error in /live-route:")
                final_route = addresses
                total_time_str = "N/A"
            else:
                route_indices = solve_tsp(matrix)  # uses the updated solve_tsp with start=0, end=n-1
                if route_indices is None:
                    current_app.logger.warning("solve_tsp returned None, using addresses as-is.")

                    final_route = addresses
                    total_time_str = "N/A"
                else:
                    final_route = [addresses[i] for i in route_indices]
                    total_sec = 0
                    for i in range(len(route_indices)-1):
                        total_sec += matrix[route_indices[i]][route_indices[i+1]]
                    total_time_str = seconds_to_hms(total_sec)
                    current_app.logger.debug("Final route computed=%s, total_time_str=%s", final_route, total_time_str)
            
            # Update cache
            if not cached_solution:
                cached_solution = RouteSolution(
                    date=selected_date,
                    route_json=json.dumps(final_route),
                    total_time_str=total_time_str,
                    last_updated=datetime.now()
                )
                db.session.add(cached_solution)
            else:
                cached_solution.route_json = json.dumps(final_route)
                cached_solution.total_time_str = total_time_str
                cached_solution.last_updated = datetime.now()
            db.session.commit()
            current_app.logger.info("Route cache updated for date=%s", selected_date)

        else:
            print("Using cached route.")
            data = cached_solution.to_dict()
            final_route = data["route"]
            total_time_str = data["total_time_str"]
            current_app.logger.debug("Using cached route with total_time_str=%s", total_time_str)

        # 7) Re-order pickups in the final route order
        route_map = {addr: idx for idx, addr in enumerate(final_route)}
        def sort_key(pr):
            full_addr = f"{pr.address}, {pr.city} CA"
            return route_map.get(full_addr, 999999)
        pickups_requested.sort(key=sort_key)

        # 8) Completed or Incomplete
        pickups_completed = PickupRequest.query.filter(
            PickupRequest.request_date == selected_date,
            or_(PickupRequest.status == 'Complete', PickupRequest.status == 'Incomplete')
        ).all()
        current_app.logger.debug("Found %d 'Requested' pickups and %d completed/incomplete pickups.", 
                                    len(pickups_requested), len(pickups_completed))
        
        current_app.logger.info("Rendering live_route.html for date=%s.", selected_date)

        return render_template(
            'admin/live_route.html',
            date=selected_date,
            pickups_requested=pickups_requested,
            pickups_completed=pickups_completed,
            route=final_route,
            pickup_status_form=pickup_status_form,
            total_time_str=total_time_str
        )


    @app.route('/toggle_pickup_status', methods=['POST'])
    @login_required
    def toggle_pickup_status():
        """
        Toggles between 'Requested' and 'Complete' (or 'Incomplete') for a given pickup.
        If new status is 'Complete', we also update driver location to this pickup's address.
        """

        current_app.logger.info("POST /toggle_pickup_status - Toggle pickup status initiated.")

        form = PickupStatusForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
            current_app.logger.debug("PickupStatusForm validated. pickup_id: %s", pickup_id)

        else:
            current_app.logger.warning("Toggle pickup status form validation failed. Errors: %s", form.errors)

            return "Error: Form validation failed", 400

        if not pickup_id:
            current_app.logger.warning("No pickup_id provided in toggle_pickup_status request.")
            return "Error: No pickup_id provided", 400

        pickup = db.session.get(PickupRequest, pickup_id)
        if not pickup:
            current_app.logger.warning("Pickup not found for pickup_id: %s", pickup_id)
            return "Error: Pickup not found, contact Sean!", 404

        # Current status could be 'Requested', 'Complete', or 'Incomplete'.
        # We want to toggle between 'Complete' and 'Requested' for this route.
        current_app.logger.info("Current pickup status for pickup_id %s is '%s'", pickup_id, pickup.status)

        if pickup.status in ["Complete", "Incomplete"]:
            current_app.logger.info("Toggling status from '%s' to 'Requested' for pickup_id: %s", pickup.status, pickup_id)

            # If current status is Complete or Incomplete -> set back to Requested
            pickup.status = "Requested"
            pickup.pickup_complete_info = None
            cached_solution = RouteSolution.query.filter_by(date=pickup.request_date).first()
            if cached_solution:
                current_app.logger.debug("Deleting cached route solution for date %s.", pickup.request_date)

                db.session.delete(cached_solution)
                db.session.commit()
        else:
            current_app.logger.info("Toggling status from 'Requested' to 'Complete' for pickup_id: %s", pickup_id)

            # Otherwise, set to Complete and record the completion time
            pickup.status = "Complete"
            pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()
            # Because the pickup was just completed, update the driver's location
            update_driver_location(pickup.address, pickup.city)

        db.session.commit()

        current_app.logger.info("Pickup status updated successfully for pickup_id: %s. New status: %s", pickup_id, pickup.status)

        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })


    @app.route('/mark-pickup-not-possible', methods=['POST'])
    @login_required
    def mark_pickup_not_possible():
        current_app.logger.info("POST /mark-pickup-not-possible - Mark pickup as not possible.")

        form = PickupStatusForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
            current_app.logger.debug("PickupStatusForm validated for mark_pickup_not_possible with pickup_id: %s", pickup_id)

        else:
            current_app.logger.warning("mark_pickup_not_possible form validation failed. Errors: %s", form.errors)
            return "Error: Form validation failed", 400

        if not pickup_id:
            current_app.logger.warning("No pickup_id provided in mark_pickup_not_possible request.")
            return "Error: No pickup_id provided", 400

        pickup = db.session.get(PickupRequest, pickup_id)

        if not pickup:
            current_app.logger.warning("Pickup not found for mark_pickup_not_possible with pickup_id: %s", pickup_id)
            return "Error: Pickup not found", 404

        # Mark the pickup as incomplete
        current_app.logger.info("Marking pickup_id %s as 'Incomplete'.", pickup_id)

        pickup.status = "Incomplete"
        pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()
        update_driver_location(pickup.address, pickup.city)

        # Notice: do not update driver location here since it's incomplete.
        db.session.commit()
        
        current_app.logger.info("Pickup marked as 'Incomplete' for pickup_id: %s", pickup_id)

        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })

    def update_driver_location(address, city):
        """
        Update the driver's location to the provided address/city.
        If no DriverLocation row exists yet, create one.
        """
        current_app.logger.info("Updating driver location to address='%s', city='%s'.", address, city)

        driver_loc = DriverLocation.query.first()
        # If you have multiple drivers, you'd filter by user_id here (DriverLocation.query.filter_by(user_id=...).first())
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
    @limiter.limit("5 per hour")   # max 5 submissions per IP per hour
    def contact_form_entry():
        form = ContactForm()
        if form.validate_on_submit():
            name    = form.name.data
            email   = form.email.data
            message = form.message.data

            current_app.logger.info(
                "Contact form validated: name=%s, email=%s", name, email
            )

            sent = send_contact_email(name, email, message)
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

    
    @app.route('/logout')
    def logout():
        current_app.logger.info("GET /logout - Logging out user and clearing session.")

        session.clear()
        return redirect(url_for('admin_login'))



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
        current_app.logger.exception("Unhandled exception occurred:")
        # send_error_report(
        #     error_type="404 Not Found",
        #     error_message=str(e),
        #     traceback_info=traceback.format_exc(),
        #     request_method=request.method,
        #     request_path=request.path,
        #     form_data=request.form.to_dict(),
        #     args_data=request.args.to_dict(),
        #     user_agent=request.headers.get('User-Agent'),
        #     remote_addr=request.remote_addr,
        # )
        return redirect(url_for('error', error_message=str(e), traceback=traceback.format_exc()))

    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Handle any other uncaught exceptions (including 500 errors).
        We email the error details, then redirect the user to /error.
        """
        print("Exception occurred.")
        current_app.logger.exception("Unhandled exception occurred:")
        # send_error_report(
        #     error_type=str(type(e)),
        #     error_message=str(e),
        #     traceback_info=traceback.format_exc(),
        #     request_method=request.method,
        #     request_path=request.path,
        #     form_data=request.form.to_dict(),
        #     args_data=request.args.to_dict(),
        #     user_agent=request.headers.get('User-Agent'),
        #     remote_addr=request.remote_addr,
        # )
        return redirect(url_for('error', error_message=str(e), traceback=traceback.format_exc()))
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return "File is too large (must be under 5mb).", 413

    @app.route('/error')
    def error():
        error=request.args.get('error_message')
        traceback=request.args.get('traceback')

        """
        A simple endpoint that displays an error page whenever something goes wrong.
        """
        return render_template('error.html', error_message=error, traceback=traceback)




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
