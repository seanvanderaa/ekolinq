# send_email.py
from flask_mail import Message
from flask import current_app  # helpful if you’re using the application factory pattern
from extensions import mail   # <--- no more "from app import mail"
from datetime import datetime

def send_contact_email(name, email, message):
    """
    Sends an email using your IONOS configuration (Flask-Mail).
    Returns True if successful, False if an error occurred.
    """
    try:
        # Subject and recipients can be customized as needed
        subject = "Testing Contact Form Submission"
        recipients = [current_app.config["MAIL_USERNAME"], "seanpvanderaa@gmail.com"]
        cc = []

        msg = Message(
            subject,
            sender=current_app.config["MAIL_USERNAME"],  # or a dedicated no-reply address
            recipients=recipients
        )
        # Construct the body of the email
        msg.body = (
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Message: \n{message}"
        )

        mail.send(msg)
        return True
    except Exception as e:
        # For production, you might log the exception or handle differently
        print(f"Error while sending email: {str(e)}")
        return False

def send_request_email(pickup):
    """
    Sends an email using your IONOS configuration (Flask-Mail).
    Returns True if successful, False if an error occurred.
    """
    try:
        # Format the first name and request ID
        first_name = pickup.fname
        request_id = pickup.request_id

        # Format the address as "123 Address, City, CA ZIP"
        address_formatted = f"{pickup.address}, {pickup.city}, CA {pickup.zipcode}"
        
        # Format the date.
        # Assume pickup.request_date is in "YYYY-MM-DD" format; if not, fallback to the raw string.
        try:
            dt = datetime.strptime(pickup.request_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%A, %b. %d")
        except Exception:
            formatted_date = pickup.request_date
        
        # Combine date and time (assuming pickup.request_time is a string like "8am-4pm")
        formatted_date_time = f"{formatted_date} between {pickup.request_time}"
        
 


        # Create the message
        subject = f"""EkoLinq: Request Confirmation for {formatted_date}"""
        recipients = [pickup.email]
        msg = Message(
            subject,
            sender=current_app.config["MAIL_USERNAME"],  # or a dedicated no-reply address
            recipients=recipients,
            bcc=['seanpvanderaa@gmail.com', current_app.config["MAIL_USERNAME"]]
        )

               # Construct the email body using the provided template with corrected placeholders.
        msg.html = f"""
        <html>
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Pick-up Request Confirmation</title>
            <!-- Using Public Sans from Google Fonts -->
            <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600&display=swap" rel="stylesheet" />
            <link href="https://fonts.googleapis.com/css?family=Open+Sans:400,600" rel="stylesheet" />
            <style>
            body {{
                font-family: 'Public Sans', 'Open Sans', sans-serif;
                margin: 0;
                padding: 0;
                background-color: #D5E1E7;
                color: #333;
            }}
            .container {{
                width: 90%;
                max-width: 600px;
                margin: 30px auto;
                background: #ffffff;
                padding: 20px 30px;
                border: 1px solid #dddddd;
                border-radius: 8px;
            }}
            h1 {{
                font-size: 22px;
                margin-bottom: 16px;
            }}
            p {{
                font-size: 16px;
            }}
            .pickup-details {{
                background: #098223;
                color: white;
                padding: 15px;
                padding-top: 7px;
                border-radius: 8px;
                margin: 36px 0;
            }}
            .pickup-details p {{
                margin: 8px 0;
                margin-bottom: 16px;
            }}
            .do-dont-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 36px 0;
            }}
            .do-dont-table th,
            .do-dont-table td {{
                padding: 10px;
                vertical-align: top;
                border: 1px solid #dddddd;
            }}
            .do-dont-table th {{
                color: #fff;
                font-size: 16px;
            }}
            .do-dont-table li {{
                margin: 8px auto;
            }}
            .do-column {{
                background-color: #098223;
                width: 50%;
            }}
            .dont-column {{
                background-color: #b14343;
                width: 50%;
            }}
            a {{
                color: #007bff;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .footer {{
                font-size: 12px;
                color: #777;
                text-align: center;
                margin-top: 30px;
            }}
            </style>
        </head>
        <body>
            <div class="container">
                <div>
                    <img src="/Creativity/EkoLinq/Website/static/images/EKOLINQ-LOGO.png" alt="Not connected/publicly hosted yet, so this image won't appear, but it will be the EkoLinq logo." width="220px" style="display: block; margin: 24px auto; margin-bottom: 48px;">
                </div>
                <p style="font-size: 18px;"><strong>Hello {first_name},</strong></p>
                <p>
                    Thank you for requesting a pick-up with <strong>EkoLinq</strong>! Below are the details of your request.
                </p>
                <div class="pickup-details">
                    <h1>Details of Your Pick-Up</h1>
                    <p><strong>Request ID:</strong><br> {request_id}</p>
                    <p><strong>Address:</strong><br> {address_formatted}</p>
                    <p><strong>Date &amp; Time:</strong><br> {formatted_date_time}</p>
                    <p style="margin-top: 24px; font-size: 14px">Something not look right? <a href="https://ekolinq.com/edit-request" style="color: #EAB308" target="_blank">Edit your request.</a></p>
                </div>
                <p style="margin: 8px 0px; margin-top: 36px;"><strong>Below are the items that we do and don't accept.</strong> Please make sure any items you leave out are acceptable! Otherwise, they will not be picked up.</p>
                <table class="do-dont-table">
                    <tr>
                        <th class="do-column">DO Accept</th>
                        <th class="dont-column">DO NOT Accept</th>
                    </tr>
                    <tr>
                        <td>
                            <ul style="padding-left: 20px; margin: 0;">
                                <li>Pants, jeans, skirts, dresses, suits, shorts, shirts</li>
                                <li>Coats, jackets, gloves, hats, scarves</li>
                                <li>Shoes, boots, heels, sneakers, sandals, socks</li>
                                <li>Bras, underwear, slips, camisoles, tights</li>
                                <li>Handbags, belts, ties, headbands</li>
                                <li>Towels, sheets, comforters, blankets, tablecloths</li>
                                <li>Wallets, totes, backpacks, stuffed animals</li>
                            </ul>
                        </td>
                        <td>
                            <ul style="padding-left: 20px; margin: 0;">
                                <li>Textiles that are wet, moldy, or contaminated with chemicals</li>
                                <li>Bio-hazardous waste</li>
                                <li>Mattresses, furniture, or other similar oversized items</li>
                            </ul>
                        </td>
                    </tr>
                </table>
                <p style="margin: 8px 0px; margin-top: 36px;">If you have any questions that we can help answer, please respond to this email!</p>
                <p style="margin: 8px 0px; margin-top: 24px;">Thanks,</p>
                <p style="margin: 8px 0px">EkoLinq Support Team</p>
                <p style="margin: 8px 0px">(866) 346-4765</p>
                <p style="margin: 8px 0px; margin-top: 16px;"><a href="mailto:contact@ekolinq.com">contact@ekolinq.com</a></p>
                <p style="margin: 8px 0px"><a href="https://ekolinq.com">www.ekolinq.com</a></p>
            </div>
        </body>
        </html>
        """

        mail.send(msg)
        return True
    except Exception as e:
        # In production, consider logging this error instead of printing it.
        print(f"Error while sending email: {str(e)}")
        return False

