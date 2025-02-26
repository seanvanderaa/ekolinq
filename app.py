# app.py
from flask import Flask, request, render_template, redirect, url_for, jsonify, make_response, session, current_app, redirect
from models import db, PickupRequest, ServiceSchedule, add_request, get_service_schedule
from config import Config
import requests
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from helpers.address import verifyZip
from helpers.contact import submitContact
from helpers.helpers import format_date
from helpers.routing import get_optimized_route
from helpers.emailer import send_email
from datetime import date, timedelta, datetime
from sqlalchemy import func
from sqlalchemy import or_
from pycognito import Cognito
from functools import wraps
import os
import csv
import io

def create_app():
    # 1) Create a Flask app
    app = Flask(__name__)

    # 2) Load .env (optional if you want environment-based overrides)
    load_dotenv()

    # 3) Load config from object
    app.config.from_object(Config)

    # 4) Initialize your extensions
    db.init_app(app)

    # 5) Create tables once if needed
    with app.app_context():
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

    @app.route('/request_pickup')
    def request_pickup():
        zipcode = request.args.get('zipcode')
        print(zipcode)
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
        return render_template('request.html', zipcode = zipcode, city=city)

    @app.route('/request_init', methods=['GET', 'POST'])
    def request_init():
        if request.method == 'POST':
            # Grab form data (posted fields)
            fname   = request.form.get('firstName')
            lname   = request.form.get('lastName')
            email   = request.form.get('email')
            address = request.form.get('address')
            city    = request.form.get('city')
            zip_    = request.form.get('zip')
            notes   = request.form.get('notes', '')
            
            # Check if 'gated' was checked in the form (it’ll be 'gated' if so, or None if not)
            gated_val = request.form.get('gated')
            gated = True if gated_val == 'gated' else False

            # For gating details
            selected_gated_option = request.form.get('selectedGatedOption')
            gate_code = request.form.get('finalGateCode') or None
            notify_val = request.form.get('finalNotice')
            notify = True if notify_val == 'true' else False



            # If user uploaded a QR code file, store the filename
            qr_code_file = request.files.get('qrCodeInput')
            qr_code_filename = None
            if qr_code_file and qr_code_file.filename:
                folder_path = 'static/images/qr_codes'
                os.makedirs(folder_path, exist_ok=True)
                qr_code_file.save(os.path.join(folder_path, qr_code_file.filename))
                qr_code_filename = qr_code_file.filename

            print(fname, lname, email, address, city, zip_, notes, gated, qr_code_filename, gate_code, notify)
            
            # Insert into DB; we can fill in request_date/time/date_filed later or set them now
            new_id = add_request(
                fname=fname,
                lname=lname,
                email=email,
                address=address,
                city=city,
                zipcode=zip_,
                notes=notes,
                gated=gated,
                qr_code=qr_code_filename,
                gate_code=gate_code,
                notify=notify,
                status="Unfinished"
                # You can also set request_date='', request_time='', date_filed='', etc.
            )

            # For demonstration, let's redirect to a "pick your date" page
            print('New ID: ', new_id)
            return redirect(url_for('select_date', request_id=new_id))

        # If GET, just show the initial form (template name is up to you)
        return render_template('request_form.html')


    @app.route('/date', methods=['GET', 'POST'])
    def select_date():
        request_id = request.args.get('request_id')
        if not request_id:
            return "Session expired, please restart.", 400
        
        pickup = db.session.get(PickupRequest, request_id)
        if not pickup:
            return "Request not found.", 404

        # Grab the schedule data (all 7 days).
        schedule_data = get_service_schedule()

        # Convert schedule_data into a dictionary for quick lookup, e.g.:
        #  {
        #    'monday': ServiceSchedule(...),
        #    'tuesday': ServiceSchedule(...),
        #    ...
        #  }
        schedule_map = {}
        for s in schedule_data:
            # e.g. "monday", "tuesday", ...
            schedule_map[s.day_of_week.lower()] = s

        # Figure out which "week" we’re on. We only allow offset from 0..2 (for 3 weeks).
        offset = request.args.get('week_offset', default=0, type=int)
        if offset < 0: 
            offset = 0
        if offset > 2: 
            offset = 2

        # The base date is "today" + X weeks
        base_date = date.today() + timedelta(weeks=offset)
        base_date_str = base_date.strftime("%b. %d")

        # Build a list of day-objects for the next 7 days from base_date
        # each day-object will contain: 
        #   {
        #     'date_obj': datetime.date(2025, 1, 11), # example
        #     'date_str': "Jan. 11",
        #     'day_of_week': "Saturday",
        #     'slots': [("08:00","12:00"), ("13:00","17:00")]  # from schedule
        #   }
        days_list = []
        for i in range(7):
            day_date = base_date + timedelta(days=i)  # date object
            day_of_week_str = day_date.strftime("%A").lower()  # e.g. "saturday"
            
            if day_of_week_str in schedule_map:
                sched = schedule_map[day_of_week_str]
                if sched.is_available:
                    # Build up to 2 time slot entries if they exist
                    slots = []
                    if sched.slot1_start and sched.slot1_end:
                        slots.append((sched.slot1_start, sched.slot1_end))
                    if sched.slot2_start and sched.slot2_end:
                        slots.append((sched.slot2_start, sched.slot2_end))

                    if slots:
                        days_list.append({
                            'date_obj': day_date,
                            'date_str': day_date.strftime("%b. %d"),  # e.g. "Jan. 11"
                            'day_of_week': day_date.strftime("%A"),   # e.g. "Saturday"
                            'slots': slots
                        })

        if request.method == 'POST':
            chosen_date = request.form.get('chosen_date')  # e.g. "2025-01-11"
            chosen_time = request.form.get('chosen_time')  # e.g. "08:00-12:00"
            
            pickup.request_date = chosen_date
            pickup.request_time = chosen_time
            pickup.status = "Requested"
            pickup.date_filed = date.today()
            db.session.commit()
            return render_template('confirmation.html', request_id=request_id, pickup=pickup)
        
        # Render the template, passing in the offset, days_list, and the request_id so we can keep it
        return render_template('select_date.html',
                            pickup=pickup,
                            days_list=days_list,
                            offset=offset,
                            max_offset=2,
                            request_id=request_id,
                            base_date_str = base_date_str)

    
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
        print("Status:", response.status_code)
        print("Response:", response.text)

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
        start_date = start_of_week
        end_date = today

        # Process form submission for a custom date range
        if request.method == 'POST':
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            if start_date_str and end_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    # Optionally add error handling for invalid dates.
                    pass

        # Build the complete date range for the period
        num_days = (end_date - start_date).days + 1
        date_range = [start_date + timedelta(days=i) for i in range(num_days)]
        daily_counts_dict = {d.strftime("%Y-%m-%d"): 0 for d in date_range}

        # Query daily pickup counts within the chosen range.
        query_result = db.session.query(
            PickupRequest.request_date,
            db.func.count(PickupRequest.id)
        ).filter(
            PickupRequest.request_date >= start_date.strftime("%Y-%m-%d"),
            PickupRequest.request_date <= end_date.strftime("%Y-%m-%d")
        ).group_by(
            PickupRequest.request_date
        ).order_by(
            PickupRequest.request_date
        ).all()

        for row in query_result:
            # Assuming request_date is stored in "YYYY-MM-DD" format.
            daily_counts_dict[row[0]] = row[1]

        # Convert to a JSON-serializable list of [date, count] pairs.
        daily_counts = [[d.strftime("%Y-%m-%d"), daily_counts_dict[d.strftime("%Y-%m-%d")]] for d in date_range]

        # Calculate total pickups for the same date range.
        pickups_total = PickupRequest.query.filter(
            PickupRequest.request_date >= start_date.strftime("%Y-%m-%d"),
            PickupRequest.request_date <= end_date.strftime("%Y-%m-%d")
        ).count()

        return render_template('admin/admin_console.html',
                            daily_counts=daily_counts,
                            pickups_this_week=pickups_total,
                            start_date=start_date.strftime("%Y-%m-%d"),
                            end_date=end_date.strftime("%Y-%m-%d"))

    @app.route('/admin-schedule', methods=['GET', 'POST'])
    @login_required
    def admin_schedule():
        # If this is a POST, we are updating the schedule
        if request.method == 'POST':
            for day in range(1,8):
                record_id     = request.form.get(f'record_{day}_id')
                is_available  = request.form.get(f'day_{day}_available') == 'on'
                slot1_start   = request.form.get(f'day_{day}_slot1_start')
                slot1_end     = request.form.get(f'day_{day}_slot1_end')
                slot2_start   = request.form.get(f'day_{day}_slot2_start')
                slot2_end     = request.form.get(f'day_{day}_slot2_end')

                schedule_record = ServiceSchedule.query.get(record_id)
                if schedule_record:
                    schedule_record.is_available = is_available
                    schedule_record.slot1_start  = slot1_start
                    schedule_record.slot1_end    = slot1_end
                    schedule_record.slot2_start  = slot2_start
                    schedule_record.slot2_end    = slot2_end
            db.session.commit()
            return redirect(url_for('admin_schedule'))

        schedule_data = get_service_schedule()
        return render_template('admin/admin_schedule.html', schedule_data=schedule_data)
    
    @app.route('/admin-pickups', methods=['GET', 'POST'])
    @login_required
    def admin_pickups():
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

        return render_template('admin/admin_pickups.html', schedule_data=schedule_data, requests=requests)

    @app.route('/admin/filtered_requests')
    @login_required
    def filtered_requests():
        query = PickupRequest.query

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
        return render_template('admin/partials/_pickup_requests_table.html', requests=requests)


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
        """
        Updates the address, city, and zipcode for a given request_id.
        Returns a JSON response indicating success or error and logs relevant information.
        """
        try:
            # Log that we received a request
            current_app.logger.info("Received request to update address.")

            # Grab the form fields
            request_id = request.form.get('request_id')
            address    = request.form.get('address')
            city       = request.form.get('city')
            zip_code   = request.form.get('zip')

            # Validate required fields
            if not request_id or not address or not city or not zip_code:
                current_app.logger.warning("Missing required fields in the form data.")
                return jsonify({
                    "status": "error",
                    "message": "Missing required fields."
                }), 400
            
            # Fetch the pickup request from the database
            pickup = db.session.get(PickupRequest, request_id)
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
            
            # Log success and return 200
            current_app.logger.info(f"Successfully updated address for request_id={request_id}")
            return render_template('confirmation.html', request_id=request_id, pickup=pickup)

        except Exception as e:
            # Log the error
            current_app.logger.error(f"Error updating address: {e}")
            return jsonify({
                "status": "error",
                "message": "An unexpected error occurred."
            }), 500
        
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

    @app.route('/live-route')
    @login_required
    def live_route():
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
        try:
            sorted_addresses, total_time_seconds, leg_times = get_optimized_route(
                addresses=requested_addresses,
                # Optional: provide start_location if you have a depot location
                start_location="5381 Mallard Dr., Pleasanton, CA",
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
        # A simple method:
        def seconds_to_hms(sec):
            hours = sec // 3600
            mins = (sec % 3600) // 60
            if hours > 0:
                return f"{hours} hr {mins} min"
            else:
                return f"{mins} min"

        total_time_str = seconds_to_hms(total_time_seconds)
        # Similarly, we could create a list of each leg’s time as strings
        leg_times_str = [seconds_to_hms(t) for t in leg_times]

        return render_template(
            'admin/live_route.html',
            date=formatted_date,
            pickups_requested=pickups_requested,
            pickups_completed=complete_incomplete_pickups,
            total_time_str=total_time_str,
            leg_times_str=leg_times_str
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
        try:
            sorted_addresses, total_time_seconds, leg_times = get_optimized_route(
                addresses=requested_addresses,
                # Optional: provide start_location if you have a depot location
                start_location="5381 Mallard Dr., Pleasanton, CA",
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

        all_pickups.sort(key=sort_key)

        # Convert total_time_seconds to a user-friendly string, e.g. "1 hr 23 min"
        # A simple method:
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
        pickup_id = request.form.get('pickup_id')

        if not pickup_id:
            return "Error: No pickup_id provided", 400

        pickup = PickupRequest.query.get(pickup_id)
        if not pickup:
            return "Error: Pickup not found", 404

        # Toggle the status
        if pickup.status == "Complete" or pickup.status == "Incomplete":
            pickup.status = "Requested"
        else:
            pickup.status = "Complete"

        db.session.commit()

        # If you prefer a redirect (page reload):
        # return redirect(url_for('live_route', date=pickup.request_date))

        # Or return JSON so the front-end can handle it without a reload:
        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })
    
    @app.route('/mark-pickup-not-possible', methods=['POST'])
    @login_required
    def mark_pickup_not_possible():
        pickup_id = request.form.get('pickup_id')

        if not pickup_id:
            return "Error: No pickup_id provided", 400

        pickup = PickupRequest.query.get(pickup_id)
        if not pickup:
            return "Error: Pickup not found", 404

        # Toggle the status
        if pickup.status:
            pickup.status = "Incomplete"

        db.session.commit()

        # If you prefer a redirect (page reload):
        # return redirect(url_for('live_route', date=pickup.request_date))

        # Or return JSON so the front-end can handle it without a reload:
        return jsonify({
            "message": "Status updated successfully",
            "new_status": pickup.status
        })

    def validate_contact(name, email, message):
        # Simple validation: all fields must be provided
        if not name or not email or not message:
            return False, "Name, email, and message are required."
        return True, ""
    
    @app.route('/contact-form-entry', methods=['GET'])
    def contact_form_entry():
        # Retrieve form data from query parameters (consider using POST for forms)
        name = request.args.get('name')
        email = request.args.get('email')
        message = request.args.get('message')
        print(name, email, message)

        valid, reason = validate_contact(name, email, message)
        if valid:
            # Send the email using the separate module
            email_sent = send_email(name, email, message)
            return jsonify({
                "valid": email_sent,
                "reason": "" if email_sent else "Email sending failed."
            })
        else:
            return jsonify({
                "valid": False,
                "reason": reason
            })
    
    @app.route('/verify_zip', methods=['GET'])
    def verify_zip():
        zip_code = request.args.get('zipcode')
        approved_zips = ["94566", "94568", "94588", "94568", "94550", "94551"]
        # Use jsonify here to properly format the JSON response
        return jsonify(verifyZip(approved_zips, zip_code))

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

# If you want app.py to be the main entry point:
if __name__ == '__main__':
    app = create_app()
    app.run(host="localhost", port=3000, debug=True)


