# app.py
from flask import Flask, request, render_template, redirect, url_for, jsonify, make_response, session, current_app, flash
from flask_wtf import CSRFProtect
from models import db, PickupRequest, ServiceSchedule, DriverLocation, RouteSolution, Config as DBConfig, add_request, get_service_schedule, get_address
from config import Config
from extensions import mail
import requests
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from helpers.address import verifyZip
from helpers.contact import submitContact
from helpers.helpers import format_date
from helpers.routing_old import get_optimized_route
from helpers.scheduling import build_schedule
from helpers.emailer import send_contact_email, send_request_email, send_error_report, send_editted_request_email
from helpers.routing import fetch_distance_matrix, solve_tsp, seconds_to_hms
from helpers.forms import RequestForm, DateSelectionForm, UpdateAddressForm, PickupStatusForm, AdminScheduleForm, AdminAddressForm, ScheduleDayForm, DateRangeForm, EditRequestTimeForm, CancelEditForm, CancelRequestForm, EditRequestInitForm, DeletePickupForm
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

csrf = CSRFProtect()

import traceback


def create_app():
    # 1) Create a Flask app
    app = Flask(__name__)

    # 2) Load .env (optional if you want environment-based overrides)
    load_dotenv()

    # 3) Load config from object
    app.config.from_object(Config)

    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' 
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 5 MB

    mail.init_app(app)
    csrf.init_app(app)

    # 4) Initialize your extensions
    db.init_app(app)

    from flask_migrate import Migrate
    migrate = Migrate(app, db)

    # 5) Create tables once if needed
    with app.app_context():
        #db.drop_all() #to reset the db
        db.create_all()
        seed_schedule_if_necessary()

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)
        return decorated_function

    @app.route('/', methods=['GET'])
    def home():
        return render_template('landing.html')
    
    @app.route('/textile-waste', methods=['GET'])
    def textileWaste():
        return render_template('textile_waste.html')
    
    @app.route('/about', methods=['GET'])
    def about():
        return render_template('about.html')

    @app.route('/request_pickup')
    def request_pickup():
        form = RequestForm()
        zipcode = request.args.get('zipcode')
        ZIP_TO_CITY = {
            "94566": "Pleasanton",
            "94568": "Dublin",
            "94588": "Pleasanton",
            "94550": "Livermore",
            "94551": "Livermore"
        }
        if zipcode in ZIP_TO_CITY:
            city = ZIP_TO_CITY[zipcode]
        else:
            city = None
            zipcode = None
        return render_template('request.html', zipcode = zipcode, city=city, form=form)


    @app.route('/request_init', methods=['GET', 'POST'])
    def request_init():
        form = RequestForm()
        if form.validate_on_submit():
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

            # Handle file upload
            qr_code_file = form.qrCodeInput.data
            qr_code_filename = None
            if qr_code_file:
                folder_path = 'static/images/qr_codes'
                os.makedirs(folder_path, exist_ok=True)
                filename = secure_filename(qr_code_file.filename)
                qr_code_file.save(os.path.join(folder_path, filename))
                qr_code_filename = filename

            print(fname, lname, email, address, city, zip_, notes, gated, qr_code_filename, gate_code, notify)
            
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
            return redirect(url_for('select_date', request_id=pickup_code))
        
        # If GET or if validation fails, render the form
        return render_template('request.html', form=form)


    @app.route('/date', methods=['GET', 'POST'])
    def select_date():
        request_id = request.args.get('request_id')
        print(request_id)
        if not request_id:
            return "Session expired, please restart.", 400

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        if not pickup:
            return "Request not found.", 404

        offset = request.args.get('week_offset', default=0, type=int)
        if offset < 0: 
            offset = 0
        if offset > 2: 
            offset = 2

        days_list, base_date_str = build_schedule(offset)
        form = DateSelectionForm()

        if form.validate_on_submit():
            chosen_date = form.chosen_date.data  # e.g., "2025-01-11"
            chosen_time = form.chosen_time.data  # e.g., "08:00-16:00"

            pickup.request_date = chosen_date
            pickup.request_time = chosen_time
            pickup.status = "Requested"
            pickup.date_filed = date.today()
            db.session.commit()

            return redirect(url_for('confirmation', request_id=request_id, pickup=pickup))
        
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
        pickup = PickupRequest.query.filter_by(request_id=request.args.get('request_id')).first()
        if pickup is None:
            return "Request not found.", 404

        send_request_email(pickup)
        update_address_form = UpdateAddressForm(obj=pickup)
        # In your confirmation route
        update_address_form.request_id.data = pickup.request_id
        update_address_form.address.data = pickup.address
        update_address_form.city.data    = pickup.city
        update_address_form.zipcode.data = pickup.zipcode
        update_address_form.page.data    = "confirmation"

        return render_template('confirmation.html', pickup=pickup, request_id=pickup.request_id, form=update_address_form)



    @app.route('/admin')
    def admin():
        return redirect(url_for('admin_console'))
    
    @app.route('/admin/login')
    def admin_login():
        client_id = os.environ.get("COGNITO_CLIENT_ID")
        domain = os.environ.get("COGNITO_DOMAIN")  # e.g., myflaskadmin.auth.us-east-1.amazoncognito.com
        redirect_uri = "http://localhost:3000/callback"
        cognito_auth_url = f"https://{domain}/login?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}"
        return redirect(cognito_auth_url)
    
    @app.route('/callback')
    def callback():
        code = request.args.get('code')
        client_id = os.environ.get("COGNITO_CLIENT_ID")
        client_secret = os.environ.get("COGNITO_CLIENT_SECRET")
        domain = os.environ.get("COGNITO_DOMAIN")
        redirect_uri = "http://localhost:3000/callback"
        
        token_url = f"https://{domain}/oauth2/token"
        data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'code': code,
            'redirect_uri': redirect_uri
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Include Authorization header if a client secret is used
        if client_secret:
            import base64
            auth_str = f"{client_id}:{client_secret}"
            b64_auth_str = base64.b64encode(auth_str.encode()).decode()
            headers['Authorization'] = f"Basic {b64_auth_str}"
        
        response = requests.post(token_url, data=data, headers=headers)

        if response.status_code == 200:
            tokens = response.json()
            # Save tokens or user info in session as needed
            session['logged_in'] = True
            session['tokens'] = tokens
            return redirect(url_for('admin_console'))
        else:
            return "Error logging in", 400
        
    @app.route('/admin-console', methods=['GET', 'POST'])
    @login_required
    def admin_console():
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
        else:
            # On GET (or if validation fails), use default dates
            start_date = default_start_date
            end_date = default_end_date
            # Pre-populate the form fields with default dates
            form.start_date.data = start_date
            form.end_date.data = end_date

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

        return render_template(
            'admin/admin_console.html',
            daily_counts=daily_counts,
            pickups_this_week=pickups_total,
            form=form  # Pass the form to your template
        )

    @app.route('/admin-schedule', methods=['GET', 'POST'])
    @login_required
    def admin_schedule():
        schedule_data = get_service_schedule()
        address = get_address()
        admin_schedule_form = AdminScheduleForm()
        admin_address_form = AdminAddressForm()

        # Populate the schedule form on GET
        if request.method == 'GET':
            for i, sched in enumerate(schedule_data):
                if i < len(admin_schedule_form.days):
                    admin_schedule_form.days[i].record_id.data = sched.id
                    admin_schedule_form.days[i].is_available.data = sched.is_available
            admin_address_form.admin_address.data = address

        # Process the POSTs—here you might want to distinguish which form is being submitted
        if request.method == 'POST':
            # Check which submit button was pressed.
            if admin_schedule_form.submit.data and admin_schedule_form.validate_on_submit():
                # Process schedule update
                for day_form in admin_schedule_form.days:
                    record_id = day_form.record_id.data
                    is_available = day_form.is_available.data
                    schedule_record = ServiceSchedule.query.get(record_id)
                    if schedule_record:
                        schedule_record.is_available = is_available
                        schedule_record.slot1_start  = "08:00"
                        schedule_record.slot1_end    = "16:00"
                        schedule_record.slot2_start  = ""
                        schedule_record.slot2_end    = ""
                db.session.commit()
                return redirect(url_for('admin_schedule'))
            elif admin_address_form.submit.data and admin_address_form.validate_on_submit():
                # Process address update
                new_address = admin_address_form.admin_address.data
                config = DBConfig.query.filter_by(key='admin_address').first()
                if config:
                    config.value = new_address
                else:
                    config = DBConfig(key='admin_address', value=new_address)
                    db.session.add(config)
                db.session.commit()
                return redirect(url_for('admin_schedule'))
            
        zipped_data = list(zip(admin_schedule_form.days, schedule_data))

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
        form = AdminAddressForm()
        if form.validate_on_submit():
            new_address = form.admin_address.data
            config = DBConfig.query.filter_by(key='admin_address').first()
            if config:
                config.value = new_address
            else:
                config = DBConfig(key='admin_address', value=new_address)
                db.session.add(config)
            db.session.commit()
            return redirect(url_for('admin_schedule'))
        else:
            return redirect(url_for('admin_schedule'))


    
    @app.route('/admin-pickups', methods=['GET', 'POST'])
    @login_required
    def admin_pickups():
        delete_form = DeletePickupForm()
        schedule_data = get_service_schedule()

        # Start with a base query for PickupRequest
        query = PickupRequest.query

        # Apply status filter if provided
        status_filter = request.args.get('status_filter')
        if status_filter:
            query = query.filter(PickupRequest.status == status_filter)

        # Apply date range filters (assuming you are filtering by date_filed)
        start_date = request.args.get('start_date')
        if start_date:
            query = query.filter(PickupRequest.request_date >= start_date)
        end_date = request.args.get('end_date')
        if end_date:
            query = query.filter(PickupRequest.request_date <= end_date)

        # Apply sorting based on user selection
        sort_by = request.args.get('sort_by')
        if sort_by == 'date_filed':
            query = query.order_by(PickupRequest.date_filed.desc())
        elif sort_by == 'date_requested':
            query = query.order_by(PickupRequest.request_date.desc())
        else:
            # Default sort (for example, by latest record)
            query = query.order_by(PickupRequest.id.desc())

        requests = query.all()

        return render_template('admin/admin_pickups.html', schedule_data=schedule_data, requests=requests, delete_form=delete_form)

    @app.route('/admin/filtered_requests')
    @login_required
    def filtered_requests():
        query = PickupRequest.query
        delete_form = DeletePickupForm()

        # Status filter
        status_filter = request.args.get('status_filter')
        if status_filter:
            query = query.filter(PickupRequest.status == status_filter)

        # Date range filters (assuming filtering by date_filed)
        start_date = request.args.get('start_date')
        if start_date:
            query = query.filter(PickupRequest.date_filed >= start_date)
        end_date = request.args.get('end_date')
        if end_date:
            query = query.filter(PickupRequest.date_filed <= end_date)

        # Sorting
        sort_by = request.args.get('sort_by')
        if sort_by == 'date_filed':
            query = query.order_by(PickupRequest.date_filed.desc())
        elif sort_by == 'date_requested':
            query = query.order_by(PickupRequest.request_date.desc())
        else:
            query = query.order_by(PickupRequest.id.desc())

        requests = query.all()
        return render_template('admin/partials/_pickup_requests_table.html', requests=requests, delete_form=delete_form)
    
    @app.route('/admin/pickups/delete', methods=['POST'])
    @login_required
    def delete_pickup():
        form = DeletePickupForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
            pickup = PickupRequest.query.get_or_404(pickup_id)
            
            db.session.delete(pickup)
            db.session.commit()
            
            flash('Pickup request deleted successfully.', 'success')
        else:
            flash('Invalid form submission.', 'danger')
        
        return redirect(url_for('admin_pickups'))


    @app.route('/admin/download_csv')
    @login_required
    def download_csv():
        # Query all pickup requests
        pickup_requests = PickupRequest.query.all()

        # Create an in-memory CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "ID", "First Name", "Last Name", "Email", "Address", "City", "Zipcode", 
            "Notes", "Gated", "QR Code", "Gate Code", "Notify", 
            "Request Date", "Request Time", "Date Filed", "Status"
        ])

        for req in pickup_requests:
            writer.writerow([
                req.id, req.fname, req.lname, req.email, req.address, req.city, req.zipcode,
                req.notes, req.gated, req.qr_code, req.gate_code, req.notify,
                req.request_date, req.request_time, req.date_filed, req.status
            ])

        # Make a Flask response with CSV data
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=pickup_requests.csv"
        response.headers["Content-type"] = "text/csv"
        return response
    
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

            current_app.logger.info("Received request to update address.")

            # Fetch the pickup request from the database
            pickup = PickupRequest.query.filter_by(request_id=request_id).first()

            if not pickup:
                current_app.logger.warning(f"No PickupRequest found for request_id={request_id}")
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
            current_app.logger.info(f"Successfully updated address for request_id={request_id}")

            # Redirect based on the page value
            if page == "edit_request":
                send_editted_request_email(pickup)
                return redirect(url_for('edit_request', request_id=request_id))
            else:
                return redirect(url_for('confirmation', request_id=request_id))
        else:
            current_app.logger.warning("Form validation failed for update address.")
            return jsonify({
                "status": "error",
                "message": "Invalid form submission."
            }), 400

        
    @app.route('/route-overview')
    @login_required
    def route_overview():
        today = date.today().strftime("%Y-%m-%d")
        
        # --- Upcoming Pickups ---
        # Query upcoming pickups grouped by date and timeframe.
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
        else:
            next_pickup = None
            remaining_upcoming = []
        
        # --- Past Pickups ---
        # Query past pickups grouped by date and timeframe.
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
        
        # Sort past dates descending.
        past_dates_sorted = sorted(past_grouped.items(), key=lambda x: x[0], reverse=True)
        past_dates_final = []
        for date_str, timeframes in past_dates_sorted:
            past_dates_final.append({
                'date': date_str,
                'formatted_date': format_date(date_str),
                'timeframes': timeframes
            })
        
        return render_template(
            "admin/route_overview.html",
            next_pickup=next_pickup,
            upcoming_dates=remaining_upcoming,
            past_dates=past_dates_final
        )

    @app.route('/live-route2')
    @login_required
    def live_route2():
        pickup_status_form = PickupStatusForm()
        selected_date = request.args.get('date')
        if not selected_date:
            return "Date parameter is required", 400

        formatted_date = format_date(selected_date)

        # Query "Requested" pickups
        pickups_requested = PickupRequest.query.filter_by(
            request_date=selected_date,
            status='Requested'
        ).all()

        # Query "Complete" pickups
        complete_incomplete_pickups = PickupRequest.query.filter(
            PickupRequest.request_date == selected_date,
            or_(PickupRequest.status == 'Complete', PickupRequest.status == 'Incomplete')
        ).all()

        # Extract addresses from the requested pickups
        requested_addresses = [p.address + ", " + p.city + " CA" for p in pickups_requested]

        # Now call our route-optimization function
        adminAddress = DBConfig.query.filter_by(key='admin_address').first()
        try:
            sorted_addresses, total_time_seconds, leg_times = get_optimized_route(
                addresses=requested_addresses,
                # Optional: provide start_location if you have a depot location
                start_location=adminAddress.value,
                api_key=os.environ.get("GOOGLE_MAPS_API_KEY")
            )
        except Exception as e:
            # Handle errors from the Directions API gracefully
            print(f"Error retrieving route info: {e}")
            sorted_addresses = requested_addresses
            total_time_seconds = 0
            leg_times = []

        # Optionally, if you want your pickups in the order the API recommends:
        # We can reorder 'pickups_requested' to match the 'sorted_addresses'.
        # This requires matching addresses. For a simple approach:
        def sort_key(pr):
            full_addr = pr.address + ", " + pr.city + " CA"
            try:
                return sorted_addresses.index(full_addr)
            except ValueError:
                return 999999  # if something doesn't match, push it to the bottom

        pickups_requested.sort(key=sort_key)

        # Convert total_time_seconds to a user-friendly string, e.g. "1 hr 23 min"
        def seconds_to_hms(sec):
            hours = sec // 3600
            mins = (sec % 3600) // 60
            if hours > 0:
                return f"{hours} hr {mins} min"
            else:
                return f"{mins} min"

        total_time_str = seconds_to_hms(total_time_seconds)
        leg_times_str = [seconds_to_hms(t) for t in leg_times]

        return render_template(
            'admin/live_route.html',
            date=formatted_date,
            pickups_requested=pickups_requested,
            pickups_completed=complete_incomplete_pickups,
            total_time_str=total_time_str,
            leg_times_str=leg_times_str,
            pickup_status_form=pickup_status_form
        )
    
    @app.route('/live-route', methods=['GET'])
    @login_required
    def live_route():
        CACHE_MAX_AGE_MINUTES = 10
        pickup_status_form = PickupStatusForm()
        selected_date = request.args.get('date')
        if not selected_date:
            return "Date parameter is required", 400
        
        # 1) Query "Requested" pickups (we exclude Completed or Incomplete)
        #    Adjust your logic if "Incomplete" is also something you'd want included.
        pickups_requested = PickupRequest.query.filter_by(
            request_date=selected_date,
            status='Requested'
        ).all()

        # 2) Determine driver's current location
        driver_loc = DriverLocation.query.first()  # or filter by user_id if multi-user
        if driver_loc and driver_loc.full_address():
            driver_current_location = driver_loc.full_address()
        else:
            # If the driver hasn't started or we haven't stored location, fall back to some default:
            # e.g. your adminAddress or depot
            admin_address = "1234 Admin St, SomeCity CA"  # or from DB
            driver_current_location = admin_address

        # 3) Build the list of addresses for the solver:
        #    Index 0 in our matrix = driver's current location
        addresses = [driver_current_location]
        
        #    Then add each requested pickup
        for p in pickups_requested:
            full_addr = f"{p.address}, {p.city} CA"
            addresses.append(full_addr)

        # 4) Attempt to load a cached route solution for this date
        cached_solution = RouteSolution.query.filter_by(date=selected_date).first()
        should_refresh = True  # default to True, we'll decide if we can skip refreshing
        
        if cached_solution:
            # Check how old it is
            age = datetime.now() - cached_solution.last_updated
            if age < timedelta(minutes=CACHE_MAX_AGE_MINUTES):
                # If it's still "fresh," we might want to skip re-calculation
                # BUT we also need to confirm that the driver's location hasn't changed 
                # or the addresses haven't changed, etc.
                # For simplicity, let's just check if the addresses match what's in the cache. 
                # If they match, we skip re-calc; if not, we recalc.
                
                cached_route_list = json.loads(cached_solution.route_json)
                # Compare the length and the first location (driver loc).
                # A more robust approach might compare sets of addresses.
                if (len(cached_route_list) == len(addresses)) and (cached_route_list[0] == driver_current_location):
                    should_refresh = False
        
        # 5) If we need to refresh, we build a new matrix and solve TSP
        final_route = []
        total_time_str = "0 min"
        
        if should_refresh:
            # fetch matrix
            try:
                matrix = fetch_distance_matrix(addresses)
            except Exception as e:
                print(f"Distance matrix error: {e}")
                # fallback: If there's an error, let's just skip optimization
                # and pass the addresses as-is
                final_route = addresses
                total_time_str = "N/A"
            else:
                # Solve TSP
                # If you want a round trip that ends back at driver's starting location, set round_trip=True
                # If you want a route that ends at the last visited address, round_trip=False
                route_indices = solve_tsp(matrix)
                if route_indices is None:
                    final_route = addresses  # fallback
                else:
                    final_route = [addresses[i] for i in route_indices]
                    
                    # compute total route time 
                    total_sec = 0
                    for i in range(len(route_indices) - 1):
                        total_sec += matrix[route_indices[i]][route_indices[i+1]]
                    total_time_str = seconds_to_hms(total_sec)
            
            # Update or create the cache entry in DB
            if cached_solution is None:
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
        
        else:
            # We can just use the cached data
            solution_data = cached_solution.to_dict()
            final_route = solution_data["route"]
            total_time_str = solution_data["total_time_str"]
        
        # 6) Re-order the pickup requests so they match the final route order
        #    final_route[0] is the driver’s current location, so we skip that in sorting.
        #    if round_trip=True, final_route[-1] will also be the driver location.
        route_map = {addr: idx for idx, addr in enumerate(final_route)}
        
        def sort_key(pr):
            full_addr = f"{pr.address}, {pr.city} CA"
            return route_map.get(full_addr, 999999)
        
        pickups_requested.sort(key=sort_key)

        complete_incomplete_pickups = PickupRequest.query.filter(
            PickupRequest.request_date == selected_date,
            or_(PickupRequest.status == 'Complete', PickupRequest.status == 'Incomplete')
        ).all()

        # 7) Render or return your data
        return render_template(
            'admin/live_route.html',
            date=selected_date,
            pickups_requested=pickups_requested,
            pickups_completed=complete_incomplete_pickups,
            route=final_route,
            pickup_status_form=pickup_status_form,
            total_time_str=total_time_str
        )


    @app.route('/view-route-info')
    @login_required
    def view_route_info():
        selected_date = request.args.get('date')
        if not selected_date:
            return "Date parameter is required", 400

        formatted_date = format_date(selected_date)

        # Query "Requested" pickups
        all_pickups = PickupRequest.query.filter_by(
            request_date=selected_date,
        ).all()

        requested_addresses = [p.address + ", " + p.city + " CA" for p in all_pickups]

        # Now call our route-optimization function
        adminAddress = DBConfig.query.filter_by(key='admin_address').first()
        try:
            sorted_addresses, total_time_seconds, leg_times = get_optimized_route(
                addresses=requested_addresses,
                # Optional: provide start_location if you have a depot location
                start_location=adminAddress.value,
                api_key=os.environ.get("GOOGLE_MAPS_API_KEY")
            )
        except Exception as e:
            # Handle errors from the Directions API gracefully
            print(f"Error retrieving route info: {e}")
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

        return render_template(
            'admin/view_route_info.html',
            date=formatted_date,
            all_pickups = all_pickups,
            total_time_str = total_time_str,
        )

    @app.route('/toggle_pickup_status', methods=['POST'])
    @login_required
    def toggle_pickup_status():
        """
        Toggles between 'Requested' and 'Complete' (or 'Incomplete') for a given pickup.
        If new status is 'Complete', we also update driver location to this pickup's address.
        """
        form = PickupStatusForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
        else:
            return "Error: Form validation failed", 400

        if not pickup_id:
            return "Error: No pickup_id provided", 400

        pickup = PickupRequest.query.get(pickup_id)
        if not pickup:
            return "Error: Pickup not found", 404

        # Current status could be 'Requested', 'Complete', or 'Incomplete'.
        # We want to toggle between 'Complete' and 'Requested' for this route.
        if pickup.status in ["Complete", "Incomplete"]:
            # If current status is Complete or Incomplete -> set back to Requested
            pickup.status = "Requested"
            pickup.pickup_complete_info = None
        else:
            # Otherwise, set to Complete and record the completion time
            pickup.status = "Complete"
            pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()
            # Because the pickup was just completed, update the driver's location
            update_driver_location(pickup.address, pickup.city)

        db.session.commit()

        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })


    @app.route('/mark-pickup-not-possible', methods=['POST'])
    @login_required
    def mark_pickup_not_possible():
        """
        Marks the pickup as 'Incomplete'. This does NOT change the driver location,
        because the pickup was never actually completed.
        """
        form = PickupStatusForm()
        if form.validate_on_submit():
            pickup_id = form.pickup_id.data
        else:
            return "Error: Form validation failed", 400

        if not pickup_id:
            return "Error: No pickup_id provided", 400

        pickup = PickupRequest.query.get(pickup_id)
        if not pickup:
            return "Error: Pickup not found", 404

        # Mark the pickup as incomplete
        pickup.status = "Incomplete"
        pickup.pickup_complete_info = datetime.now().strftime("%Y-%m-%d %-I:%M%p").lower()
        update_driver_location(pickup.address, pickup.city)

        # Notice: do not update driver location here since it's incomplete.
        db.session.commit()

        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })

    def update_driver_location(address, city):
        """
        Update the driver's location to the provided address/city.
        If no DriverLocation row exists yet, create one.
        """
        driver_loc = DriverLocation.query.first()
        # If you have multiple drivers, you'd filter by user_id here (DriverLocation.query.filter_by(user_id=...).first())
        if not driver_loc:
            driver_loc = DriverLocation(address=address, city=city)
            db.session.add(driver_loc)
        else:
            driver_loc.address = address
            driver_loc.city = city

        db.session.commit()

    def validate_contact(name, email, message):
        if not name or not email or not message:
            return False, "Name, email, and message are required."
        return True, ""

    @app.route('/contact-form-entry', methods=['GET'])
    def contact_form_entry():
        name = request.args.get('name')
        email = request.args.get('email')
        message = request.args.get('message')

        valid, reason = validate_contact(name, email, message)
        if valid:
            email_sent = send_contact_email(name, email, message)
            return jsonify({"valid": email_sent,
                            "reason": "" if email_sent else "Email sending failed."})
        else:
            return jsonify({"valid": False, "reason": reason})

    @app.route('/edit-request/check', methods=['POST'])
    def edit_request_check():
        form = EditRequestInitForm()
        if form.validate_on_submit():
            request_id = form.request_id.data
            email = form.email.data

        # Validate format: must be exactly 6 digits
        if not request_id.isdigit() or len(request_id) != 6:
            return jsonify({
                'success': False,
                'error': 'Your code must be exactly 6 digits and cannot contain any other characters. Please check and try again.'
            }), 400

        # Attempt to find matching row in DB
        pickup_request = PickupRequest.query.filter_by(request_id=request_id).first()
        if not pickup_request:
            return jsonify({
                'success': False,
                'error': (
                    "Not found. Please make sure the number matches exactly "
                    "what appears in your confirmation email, and try again."
                )
            }), 404
        
        if pickup_request.email != email:
            return jsonify({
                'success': False,
                'error': (
                    "The code and email do not match. Please verify the info you entered is correct and try again."
                    " If you think this is a mistake, please contact us."
                )
            }), 400

        if pickup_request.request_date:
            try:
                request_date_obj = datetime.strptime(pickup_request.request_date, '%Y-%m-%d').date()
                if request_date_obj < datetime.today().date():
                    return jsonify({
                        'success': False,
                        'error': (
                            "Your request date has already passed "
                            "and can no longer be edited. "
                            "If you think this is an error, please contact us."
                        )
                    }), 400
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': (
                        "We couldn't verify the request date. "
                        "Please contact us for further assistance."
                    )
                }), 400
            
        if pickup_request.status == "Cancelled":
            return jsonify({
                'success': False,
                'error': (
                    "Your request has previously been cancelled and can no longer be edited."
                    " If you think this is a mistake, please contact us."
                )
            }), 400
        
        if pickup_request.status == "Completed":
            return jsonify({
                'success': False,
                'error': (
                    "Your request has been completed and can no longer be edited."
                    " If you think this is a mistake, please contact us."
                )
            }), 400

        return jsonify({'success': True}), 200
    

    @app.route('/edit-request-init', methods=['GET'])
    def edit_request_init():
        edit_request_form = EditRequestInitForm()
        return render_template(
            'edit_request.html',
            edit_request_form=edit_request_form,
            partial="/partials/_editRequest_init.html"
        )

    
    @app.route('/edit-request', methods=['GET', 'POST'])
    @csrf.exempt
    def edit_request():
        if request.method == "GET":
            request_id = request.args.get('request_id', '').strip()
            print(request_id)
            if not request_id:
                return redirect(url_for('edit_request_init'))
            
            pickup = PickupRequest.query.filter_by(request_id=request_id).first()
            if not pickup:
                return redirect(url_for('edit_request_init'))
            pickup = PickupRequest.query.filter_by(request_id=request_id).first()

            update_address_form = UpdateAddressForm(obj=pickup)
            update_address_form.request_id.data = pickup.request_id
            update_address_form.address.data = pickup.address
            update_address_form.city.data    = pickup.city
            update_address_form.zipcode.data = pickup.zipcode
            update_address_form.page.data    = "edit_request"

            cancel_form = CancelRequestForm()
            cancel_form.request_id.data = pickup.request_id

            return render_template('edit_request.html',
                                partial="/partials/_editRequest_info.html",
                                pickup=pickup,
                                max_offset=2,
                                request_id=request_id,
                                form=update_address_form,
                                cancel_form=cancel_form)
        else:
            # Use a separate form for cancellation
            cancel_form = CancelEditForm()
            if cancel_form.validate_on_submit():
                request_id = cancel_form.request_id.data
                # Process cancellation (e.g., simply re-render the edit page)
                pickup = PickupRequest.query.filter_by(request_id=request_id).first()
                # You might want to log a cancellation action, reset some state, or simply redirect:
                return redirect(url_for('edit_request', request_id=request_id))
            else:
                current_app.logger.error("CancelEditForm validation errors: %s", cancel_form.errors)
                return "Validation failed: " + str(cancel_form.errors), 400
        
    @app.route('/edit-request-time', methods=['GET'])
    def edit_request_time():
        time_form = EditRequestTimeForm()
        request_id = request.args.get('request_id')
        if not request_id:
            return "Session expired, please restart.", 400

        pickup = PickupRequest.query.filter_by(request_id=request_id).first()
        time_form.request_id.data = pickup.request_id
        if not pickup:
            return 404

        offset = request.args.get('week_offset', default=0, type=int)
        if offset < 0: 
            offset = 0
        if offset > 2: 
            offset = 2

        offset = request.args.get('week_offset', default=0, type=int)
        
        days_list, base_date_str = build_schedule(offset)

        update_address_form = UpdateAddressForm(obj=pickup)

        cancel_form = CancelRequestForm()
        cancel_form.request_id.data = pickup.request_id

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
        form = EditRequestTimeForm()
        print("at form")
        if form.validate_on_submit():
            print("form valid")
            request_id = form.request_id.data
            chosen_date = datetime.strptime(form.chosen_date.data, "%Y-%m-%d").date()
            chosen_time = form.chosen_time.data

            pickup = PickupRequest.query.filter_by(request_id=request_id).first()
            if not pickup:
                # Optionally flash an error message here
                return redirect(url_for('edit_request'))
            
            pickup.request_date = chosen_date
            pickup.request_time = chosen_time
            pickup.status = "Requested"
            pickup.date_filed = date.today()
            db.session.commit()

            send_editted_request_email(pickup)

            return redirect(url_for('edit_request', request_id=request_id))
        else:
            print("Form errors:", form.errors)
            # Optionally log or flash the errors from form.errors here for debugging
            return redirect(url_for('edit_request'))


    
    @app.route('/verify_zip', methods=['GET'])
    def verify_zip():
        zip_code = request.args.get('zipcode')
        approved_zips = ["94566", "94568", "94588", "94568", "94550", "94551"] 
        return jsonify(verifyZip(approved_zips, zip_code))
    
    @app.route('/cancel-request', methods=["POST"])
    def cancel_request():
        form = CancelRequestForm()
        if form.validate_on_submit():
            request_id = form.request_id.data
            pickup = PickupRequest.query.filter_by(request_id=request_id).first()

            if not pickup:
                return jsonify({
                    "valid": False,
                    "reason": "Pickup not found."
                }), 404
            pickup.status = "Cancelled"
            db.session.commit()
            if pickup.status == "Cancelled":
                return jsonify({
                    "valid": True,
                    "reason": "Request cancelled."
                })
            else:
                return jsonify({
                    "valid": False,
                    "reason": "Unable to cancel your request. Please contact us for further support."
                })
        else:
            return jsonify({
                "valid": False,
                "reason": "Invalid form submission.",
                "errors": form.errors
            }), 400



    @app.cli.command('reset-db')
    def reset_db():
        """Drops all tables and recreates them."""
        with app.app_context():
            print("Dropping all tables...")
            db.drop_all()
            print("Creating all tables...")
            db.create_all()
            print("Database reset complete.")

    # --------------------------------------------------
    # NEW ERROR HANDLERS & /error ENDPOINT
    # --------------------------------------------------
    @app.errorhandler(404)
    def handle_404(e):
        """
        Handle 'page not found' errors. We email the error details, then
        redirect the user to the /error page.
        """
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
        print("Here! 2")
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

# If you want app.py to be the main entry point:
if __name__ == '__main__':
    app = create_app()
    app.run(host="localhost", port=3000, debug=True)
