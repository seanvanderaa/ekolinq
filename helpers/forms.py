# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SelectField, TextAreaField, FileField, HiddenField
from wtforms.fields import EmailField
from wtforms.validators import DataRequired, Email, Optional

class RequestForm(FlaskForm):
    # Contact Info
    firstName = StringField("First Name", validators=[Optional()])
    lastName = StringField("Last Name", validators=[Optional()])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Phone Number", validators=[Optional()])
    
    # Address
    address = StringField("Address", validators=[DataRequired()])
    city = StringField("City", validators=[DataRequired()])
    zip = StringField("Zip Code", validators=[DataRequired()])
    
    # Additional Notes
    notes = TextAreaField("Notes", validators=[Optional()])
    
    # Gated Info
    gated = BooleanField("Gated")
    gatedOptions = SelectField("Gated Options", choices=[
        ("", "-- Select Option --"),
        ("code", "Provide a gate code"),
        ("qr", "Upload a QR code"),
        ("notice", "I will notify our community access attendant")
    ], validators=[Optional()])
    gateCodeInput = StringField("Gate Code", validators=[Optional()])
    qrCodeInput = FileField("QR Code", validators=[Optional()])
    # Hidden fields for final gating data (if needed)
    selectedGatedOption = HiddenField("Selected Gated Option", validators=[Optional()])
    finalGateCode = HiddenField("Final Gate Code", validators=[Optional()])
    finalNotice = HiddenField("Final Notice", validators=[Optional()])

class DateSelectionForm(FlaskForm):
    chosen_date = HiddenField('Chosen Date', validators=[DataRequired()])
    chosen_time = HiddenField('Chosen Time', validators=[DataRequired()])

class UpdateAddressForm(FlaskForm):
    request_id = HiddenField("Request ID", validators=[DataRequired()])
    address    = StringField("Address", validators=[DataRequired()])
    city       = StringField("City", validators=[DataRequired()])
    zipcode    = StringField("Zip Code", validators=[DataRequired()])
    page       = HiddenField("Page", validators=[DataRequired()])