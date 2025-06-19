# forms.py
from flask_wtf import FlaskForm, RecaptchaField
from wtforms import StringField, BooleanField, SelectField, TextAreaField, FileField, HiddenField, FieldList, FormField, SubmitField, ValidationError
from wtforms.fields import EmailField, DateField, RadioField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp, InputRequired
import requests, urllib.parse
from flask import current_app

class RequestForm(FlaskForm):
    # Contact Info
    firstName = StringField("First Name", validators=[
        Optional(), Length(max=50)
    ])
    lastName = StringField("Last Name", validators=[
        Optional(), Length(max=50)
    ])
    email = EmailField("Email", validators=[
        DataRequired(), Email(), Length(max=120)
    ])
    phone = StringField("Phone Number", validators=[
        DataRequired(), Length(max=20),
        Regexp(r'^\+?[0-9\-\s]*$', message="Invalid phone number format")
    ])
    
    # Address
    address = StringField("Address", validators=[
        DataRequired(), Length(max=200)
    ])
    city = StringField("City", validators=[
        DataRequired(), Length(max=100)
    ])
    zip = StringField("Zip Code", validators=[
        DataRequired(),
        Regexp(r'^\d{5}(-\d{4})?$', message="Invalid zip code format")
    ])
    
    # Additional Notes
    notes = TextAreaField("Notes", validators=[
        Optional(), Length(max=1000)
    ])
    
    # Gated Info
    gated = RadioField(
        "Do we need a gate code or permission to access your address?",
        choices=[("yes", "Yes"), ("no", "No")],
        coerce=lambda v: v == "yes", 
        validators=[InputRequired(message="Please choose either 'Yes' or 'No'")]
    )
    place_id = StringField()        

    awarenessOptions = SelectField(
        "How did you hear about us?",
        choices=[
            ("", "-- Select Option --"),
            ("Referral", "Referral"),
            ("Facebook", "Facebook"),
            ("Nextdoor", "Nextdoor"),
            ("Other social media", "Other social media"),
            ("Internet search", "Internet search"),
            ("Seen", "Saw EkoLinq around town"),
            ("Mailer", "Received a mailer"),
            ("Online website", "An online website (Zero Waste, Stopwaste.org, etc.)"),
            ("Other", "Other"),
        ],
        validators=[DataRequired()]
    )

    recaptcha = RecaptchaField()
    # --------------------------------------------------
    # GLOBAL VALIDATOR
    # --------------------------------------------------
    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False              # built-ins failed first

        # 1) Compose the full address
        full_addr = f"{self.address.data}, {self.city.data} {self.zip.data}"

        try:
            _verify(full_addr, self.place_id.data)
        except ValidationError as ve:
            self.address.errors.append(str(ve))
            return False
        except Exception:
            self.address.errors.append("Address validation service unavailable. Please try again.")
            return False

        return True   # all good


# ---------------- provider helpers ----------------

def _verify(full_addr: str, place_id: str):
    """Raise ValidationError if address cannot be confirmed."""
    key = current_app.config["GOOGLE_API_KEY"]
    if place_id:                                       # fastest path
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "key": key, "fields": "formatted_address"}
        )
        data = resp.json()
        if data.get("status") == "OK":
            return
    # fallback: forward-geocode the string
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": full_addr, "key": key, "components": "country:US"}
    )
    data = resp.json()
    if data.get("status") != "OK" or not data["results"]:
        raise ValidationError("Address not found—please check spelling.")
    # ⬆ We don’t need to compare exact strings—Google found it, that’s enough.



class EditRequestTimeForm(FlaskForm):
    chosen_date = HiddenField('Chosen Date', validators=[DataRequired()])
    chosen_time = HiddenField('Chosen Time', validators=[DataRequired()])
    request_id = HiddenField("Pickup ID", validators=[DataRequired()])


class DateSelectionForm(FlaskForm):
    chosen_date = HiddenField('Chosen Date', validators=[DataRequired()])
    chosen_time = HiddenField('Chosen Time', validators=[DataRequired()])


class UpdateAddressForm(FlaskForm):
    request_id = HiddenField("Request ID", validators=[DataRequired()])
    address    = StringField("Address", validators=[
        DataRequired(), Length(max=200)
    ])
    city       = StringField("City", validators=[
        DataRequired(), Length(max=100)
    ])
    zipcode    = StringField("Zip Code", validators=[
        DataRequired(),
        Regexp(r'^\d{5}(-\d{4})?$', message="Invalid zip code format")
    ])
    page       = HiddenField("Page", validators=[DataRequired()])

class PickupStatusForm(FlaskForm):
    pickup_id = HiddenField("Pickup ID", validators=[DataRequired()])

class ScheduleDayForm(FlaskForm):
    record_id = HiddenField('Record ID', validators=[DataRequired()])
    is_available = BooleanField('Available?', validators=[Optional()])

class AdminScheduleForm(FlaskForm):
    # We expect exactly 7 days (or however many your schedule_data has)
    days = FieldList(FormField(ScheduleDayForm), min_entries=7)
    submit = SubmitField('Save Schedule')

class AdminAddressForm(FlaskForm):
    admin_address = StringField('Admin Address', validators=[DataRequired()])
    submit = SubmitField('Update Address')

class DateRangeForm(FlaskForm):
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Filter')

class FilterRequestsForm(FlaskForm):
    sort_by = SelectField('Sort By', choices=[
        ('', 'Default'),
        ('date_filed', 'Date Filed'),
        ('date_requested', 'Date Requested')
    ], validators=[Optional()])
    
    status_filter = SelectField('Status', choices=[
        ('', 'All'),
        ('Unfinished', 'Unfinished'),
        ('Requested', 'Requested'),
        ('Complete', 'Complete'),
        ('Incomplete', 'Incomplete'),
        ('Cancelled', 'Cancelled')
    ], validators=[Optional()])
    
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])

class CancelEditForm(FlaskForm):
    request_id = HiddenField("Request ID", validators=[DataRequired(), Regexp(r'^\d+$', message="Invalid request ID")])

class CancelRequestForm(FlaskForm):
    request_id = HiddenField("Request ID", validators=[DataRequired()])

class EditRequestInitForm(FlaskForm):
    request_id = StringField("Request ID", validators=[DataRequired()])
    requester_email = EmailField("Email", validators=[
        DataRequired(), Email(), Length(max=120)
    ])
    recaptcha = RecaptchaField()

class updateCustomerNotes(FlaskForm):
    request_id = HiddenField(validators=[DataRequired()])
    notes = TextAreaField(
        'Notes',
        validators=[Length(max=400)]
    )
    submit = SubmitField("Save Notes")

class DeletePickupForm(FlaskForm):
    pickup_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Delete')

class ContactForm(FlaskForm):
    name = StringField(
        'Name',
        validators=[DataRequired(), Length(max=128)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(), Length(max=256)]
    )
    message = TextAreaField(
        'Message',
        validators=[DataRequired(), Length(max=2000)]
    )
    # Override default message
    recaptcha = RecaptchaField()

class CleanPickupsForm(FlaskForm):
    submit = SubmitField("Clean Up and Update Google Spreadsheet")

class AddPickupNotes(FlaskForm):
    pickup_id = HiddenField(validators=[DataRequired()])
    admin_notes = TextAreaField(
        'Notes',
        validators=[DataRequired(), Length(max=2000)]
    )
    submit = SubmitField("Update Notes")
