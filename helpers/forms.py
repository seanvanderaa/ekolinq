# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SelectField, TextAreaField, FileField, HiddenField, FieldList, FormField, SubmitField
from wtforms.fields import EmailField, DateField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp

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
    gated = BooleanField("Gated")
    gatedOptions = SelectField("Gated Options", choices=[
        ("", "-- Select Option --"),
        ("code", "Provide a gate code"),
        ("qr", "Upload a QR code"),
        ("notice", "I will notify our community access attendant")
    ], validators=[Optional()])
    gateCodeInput = StringField("Gate Code", validators=[
        Optional(), Length(max=20)
    ])
    qrCodeInput = FileField("QR Code", validators=[Optional()])
    # Hidden fields for final gating data (if needed)
    selectedGatedOption = HiddenField("Selected Gated Option", validators=[Optional()])
    finalGateCode = HiddenField("Final Gate Code", validators=[Optional()])
    finalNotice = HiddenField("Final Notice", validators=[Optional()])

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

class DeletePickupForm(FlaskForm):
    pickup_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Delete')