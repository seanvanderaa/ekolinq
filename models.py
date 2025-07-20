# models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
import random
from datetime import datetime
import json

db = SQLAlchemy()

class PickupRequest(db.Model):
    __tablename__ = 'pickup_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    fname = db.Column(db.String(100), nullable=True)
    lname = db.Column(db.String(100), nullable=True)

    email = db.Column(db.String(120), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)

    address = db.Column(db.String(200), nullable=False)
    address2 = db.Column(db.String(200), nullable=True)
    
    city = db.Column(db.String(200), nullable=False)
    zipcode = db.Column(db.String(10), nullable=False)

    geocoded_addr = db.Column(db.String(50), nullable=True)

    notes = db.Column(db.String(400), nullable=True)
    status = db.Column(db.String(50), default='Pending')
    
    gated = db.Column(db.Boolean, default=False, nullable=True)

    awareness = db.Column(db.String(120), nullable=False)
    
    request_date = db.Column(db.String(120), nullable=True)
    request_time = db.Column(db.String(120), nullable=True)
    
    date_filed = db.Column(db.String(120), nullable=True)

    pickup_complete_info = db.Column(db.String(120), nullable=True)

    request_id = db.Column(db.String(8), unique=True, nullable=False)

    admin_notes = db.Column(db.String(2000), nullable=True)


import string
import secrets
_BASE62 = string.ascii_uppercase + string.digits

def generate_unique_request_id(length: int = 8, max_attempts: int = 20) -> str:
    """
    Return an 8-character, URL-safe ID that is (a) unpredictable and
    (b) unique in the PickupRequest table.
    """
    for _ in range(max_attempts):
        code = ''.join(secrets.choice(_BASE62) for _ in range(length))
        if not PickupRequest.query.filter_by(request_id=code).first():
            return code

    raise RuntimeError("Could not generate a unique request_id; "
                       "increase length or investigate DB state.")

@event.listens_for(PickupRequest, 'before_insert')
def assign_request_id(mapper, connection, target):
    # If no request_id is set, generate one.
    if not target.request_id:
        target.request_id = generate_unique_request_id()


class ServiceSchedule(db.Model):
    __tablename__ = 'service_schedule'
    
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(10), nullable=False)  # e.g. "Monday", "Tuesday", ...
    is_available = db.Column(db.Boolean, default=False)
    
    slot1_start = db.Column(db.String(5), nullable=True)  # e.g. "08:00"
    slot1_end   = db.Column(db.String(5), nullable=True)  # e.g. "12:00"
    slot2_start = db.Column(db.String(5), nullable=True)  # e.g. "13:00"
    slot2_end   = db.Column(db.String(5), nullable=True)  # e.g. "17:00"

class ContactEntries(db.Model):
    __tablename__ = 'contact_form_entries'

    id = db.Column(db.Integer, primary_key=True)

    submitDate = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    message = db.Column(db.String(1000), nullable=True)

class Config(db.Model):
    __tablename__ = 'config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.String(256), nullable=False)

def reset_db():
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()
    print("Database reset complete.")

def get_service_schedule():
    """
    Returns a list of ServiceSchedule entries for all 7 days of the week
    (or however many you choose to store).
    """
    return ServiceSchedule.query.order_by(ServiceSchedule.id).all()

def get_address():
    config = Config.query.filter_by(key='admin_address').first()
    return config.value if config else None

def add_request(**kwargs):
    new_pickup = PickupRequest(**kwargs)
    db.session.add(new_pickup)
    db.session.commit()
    return new_pickup.id

class RouteSolution(db.Model):
    """
    Table to cache/store the solved route for a given date (or driver, if multiple).
    """
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)  
    route_json = db.Column(db.Text, nullable=True)
    total_time_str = db.Column(db.String(50), nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now)
    legs_json = db.Column(db.Text)
    needs_refresh = db.Column(db.Boolean, default=False, nullable=False)

    
    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "route": json.loads(self.route_json) if self.route_json else [],
            "total_time_str": self.total_time_str,
            "last_updated": self.last_updated.isoformat()
        }


class DriverLocation(db.Model):
    """
    Stores the driver's last known location, so the route can start from there.
    This is useful once they've begun making pickups.
    """
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now(), onupdate=datetime.now())

    def full_address(self):
        return f"{self.address}, {self.city} CA" if (self.address and self.city) else None
    
class SiteRating(db.Model):
    """
    Stores the driver's last known location, so the route can start from there.
    This is useful once they've begun making pickups.
    """
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(8), nullable=False)
    rating = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.String(400), nullable=True)