# emailer.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(name, sender_email, message):
    # SMTP server configuration (Gmail example)
    smtp_server = "smtp.gmail.com"
    port = 587
    login = "seanpvanderaa@gmail.com"        # Replace with your email address
    password = "MoreGarlic420#"          # Use your app-specific password if needed

    # The email will be sent to this address (e.g., your support inbox)
    recipient_email = "seanpvanderaa@gmail.com"  # Replace with your destination email
    subject = f"Contact Form Submission from {name}"

    # Build the email message
    msg = MIMEMultipart()
    msg["From"] = login
    msg["To"] = recipient_email
    msg["Subject"] = subject

    # Email body
    body = f"Name: {name}\nEmail: {sender_email}\nMessage: {message}"
    msg.attach(MIMEText(body, "plain"))

    try:
        # Connect to the server and send the email
        # server = smtplib.SMTP(smtp_server, port)
        # server.ehlo()
        # server.starttls()
        # server.ehlo()
        # server.login(login, password)
        # server.sendmail(login, recipient_email, msg.as_string())
        # server.quit()
        return True
    except Exception as e:
        print("Error sending email:", e)
        return False
