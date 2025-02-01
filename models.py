# models.py
from flask_sqlalchemy import SQLAlchemy

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

def add_request(**kwargs):
    new_pickup = PickupRequest(**kwargs)
    db.session.add(new_pickup)
    db.session.commit()
    return new_pickup.id



class ServiceSchedule(db.Model):
    __tablename__ = 'service_schedule'
    
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(10), nullable=False)  # e.g. "Monday", "Tuesday", ...
    is_available = db.Column(db.Boolean, default=False)
    
    slot1_start = db.Column(db.String(5), nullable=True)  # e.g. "08:00"
    slot1_end   = db.Column(db.String(5), nullable=True)  # e.g. "12:00"
    slot2_start = db.Column(db.String(5), nullable=True)  # e.g. "13:00"
    slot2_end   = db.Column(db.String(5), nullable=True)  # e.g. "17:00"

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
