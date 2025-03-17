# models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
import random

db = SQLAlchemy()

class PickupRequest(db.Model):
    __tablename__ = 'pickup_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    fname = db.Column(db.String(100), nullable=True)
    lname = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(200), nullable=False)
    zipcode = db.Column(db.String(10), nullable=False)
    notes = db.Column(db.String(400), nullable=True)
    status = db.Column(db.String(50), default='Pending')
    
    gated = db.Column(db.Boolean, default=False)
    qr_code = db.Column(db.String(255), nullable=True)
    gate_code = db.Column(db.String(50), nullable=True)
    notify = db.Column(db.Boolean, default=False)
    
    request_date = db.Column(db.String(120), nullable=True)
    request_time = db.Column(db.String(120), nullable=True)
    
    date_filed = db.Column(db.String(120), nullable=True)

    request_id = db.Column(db.String(6), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)

def generate_unique_request_id():
    # Generate a random 6-digit code as a string.
    code = str(random.randint(100000, 999999))
    # Keep generating until the code is unique.
    while PickupRequest.query.filter_by(request_id=code).first() is not None:
        code = str(random.randint(100000, 999999))
    return code

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