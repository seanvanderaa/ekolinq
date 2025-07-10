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
    Sends a pick‑up request confirmation email.

    If ``pickup.gated`` is truthy, a highlighted banner will be injected beneath the
    logo reminding the recipient to provide gate access details. Otherwise the
    banner is omitted entirely.

    Returns ``True`` when the email is dispatched successfully, ``False`` when an
    exception is raised.
    """
    try:
        # --- Setup -----------------------------------------------------------------
        mail = current_app.extensions.get("mail")

        first_name = ' ' + pickup.fname
        request_id = pickup.request_id
        if pickup.address2: 
            address_formatted = f"{pickup.address} {pickup.address2}, {pickup.city}, CA {pickup.zipcode}"
        else:
            address_formatted = f"{pickup.address}, {pickup.city}, CA {pickup.zipcode}"
        gated = bool(pickup.gated)

        try:
            dt = datetime.strptime(pickup.request_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%A, %b. %d")
        except Exception:
            formatted_date = pickup.request_date

        formatted_date_time = f"{formatted_date} between 8am-4pm"

        # ---------------------------------------------------------------------------
        # Subject & Recipients
        # ---------------------------------------------------------------------------
        subject = f"EkoLinq: Request Confirmation for {formatted_date}"
        recipients = [pickup.email]
        msg = Message(
            subject=subject,
            sender=current_app.config["MAIL_USERNAME"],
            recipients=recipients,
            bcc=["seanpvanderaa@gmail.com", current_app.config["MAIL_USERNAME"]],
        )

        # ---------------------------------------------------------------------------
        # Conditional gated‑access notice (inlined for email safety)
        # ---------------------------------------------------------------------------
        gated_notice_html = ""
        if gated:
            gated_notice_html = (
                "<div style=\"background:#EAB308; color:black; border:1px solid #ffeeba; "
                "padding:16px; border-radius:8px; margin:0 0 32px 0; font-size:15px; line-height:1.4;\">"
                "<strong>Notice:</strong> You indicated that we need a code or permission to access your address. "
                "Please reply to this email with the access code (number, QR code, etc.) or confirm that you have "
                "notified your gate attendant about our arrival." 
                "</div>"
            )

        # ---------------------------------------------------------------------------
        # Compose the HTML body
        # ---------------------------------------------------------------------------
        msg.html = f"""
        <html>
          <head>
            <meta charset=\"UTF-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
            <title>Pick-up Request Confirmation</title>
            <link href=\"https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap\" rel=\"stylesheet\" />
            <style>
              body, p, h1, h2, h3, td, li, a {{
                font-family: 'Public Sans', Arial, sans-serif !important;
              }}
            </style>
          </head>
          <body style=\"margin:0; padding:24px 0; background-color:#104378; color:#000;\">
            <div style=\"width:90%; max-width:600px; margin:30px auto; background:#fff; padding:20px 30px 32px; border:1px solid #ddd; border-radius:40px;\">
              <div style=\"text-align:center;\">
                <img src=\"https://i.imgur.com/g6QpslJ.png\" alt=\"EkoLinq Logo\" width=\"140\" style=\"display:block; margin:36px auto 24px; margin-bottom: 24px\" />
              </div>
              <h1 style=\"font-size:16px; margin-bottom:16px; margin-top: 16px; font-weight: 500; text-align:center; margin-bottom: 24px\">Pickup Request Confirmation</h1>
              {gated_notice_html}
              <p style=\"font-size:18px; margin-top:36px;\">Hello{first_name},</p>
              <p style=\"font-size:16px;\">Thanks for choosing to get rid of waste the right way. Below is the information for your pick-up request. <b>Please remember to have your items out by 8AM on the day of your pick-up.</b></p>
              <div style=\"background:#098223; color:#fff; padding:16px; border-radius:8px; margin:48px 0;\">
                <p style=\"margin:12px 0 8px; font-size:14px; font-weight:200;\">Request ID</p>
                <p style=\"margin:0; font-weight:500; font-size:16px;\">{request_id}</p>
                <p style=\"margin:12px 0 8px; font-size:14px; font-weight:200;\">Address</p>
                <p style=\"margin:0; font-weight:500; font-size:16px;\">{address_formatted}</p>
                <p style=\"margin:12px 0 8px; font-size:14px; font-weight:200;\">Date &amp; Time</p>
                <p style=\"margin:0; font-weight:500; font-size:16px;\">{formatted_date_time}</p>
                <a href=\"https://ekolinq.com/edit-request\" style=\"text-decoration:none;\">
                  <p style=\"margin-top:36px; border-radius:5px; padding:12px 16px; color:#000; background-color:#EAB308; width:120px; text-align:center; font-weight:500; font-size:16px;\">Edit Details</p>
                </a>
              </div>
              <h3 style=\"margin-top:36px; font-size:20px;\">Reminder: Here's what you can and can't give us</h3>
              <table style=\"width:100%; border-collapse:separate;\" cellspacing=\"4\">
                <tr>
                  <td style=\"vertical-align:top; width:50%;\">
                    <table style=\"width:100%; border:1px solid #c6c6c6; border-radius:10px; padding:10px; background:#fff; padding-bottom:24px;\">
                      <tr>
                        <th style=\"font-size:20px; padding:10px; text-align:left; font-weight:bold;\">
                          <span style=\"color:#098223; font-size:24px; margin-right:12px; vertical-align:middle;\">&#10003;</span>
                          DO Accept
                        </th>
                      </tr>
                      <tr>
                        <td style=\"padding:10px;\">
                          <ul style=\"padding-left:20px; margin:0;\">
                            <li style=\"margin:8px 0; font-size:16px;\">Pants, jeans, skirts, dresses, suits, shorts, shirts</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Coats, jackets, gloves, hats, scarves</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Shoes, boots, heels, sneakers, sandals, socks</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Bras, underwear, slips, camisoles, tights</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Handbags, belts, ties, headbands</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Towels, sheets, comforters, blankets, tablecloths</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Wallets, totes, backpacks, stuffed animals</li>
                          </ul>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td style=\"vertical-align:top; width:50%;\">
                    <table style=\"width:100%; border:1px solid #c6c6c6; border-radius:10px; padding:10px; background:#fff; padding-bottom:24px;\">
                      <tr>
                        <th style=\"font-size:20px; padding:10px; text-align:left; font-weight:bold;\">
                          <span style=\"color:red; font-size:24px; margin-right:12px; vertical-align:middle;\">&#10005;</span>
                          DON'T Accept
                        </th>
                      </tr>
                      <tr>
                        <td style=\"padding:10px;\">
                          <ul style=\"padding-left:20px; margin:0;\">
                            <li style=\"margin:8px 0; font-size:16px;\">Textiles that are wet, moldy, or contaminated with chemicals</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Bio-hazardous waste</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Pillows and cushions</li>
                            <li style=\"margin:8px 0; font-size:16px;\">Mattresses, furniture, or other similar oversized items</li>
                          </ul>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              <p style=\"font-size:16px; margin-top:36px;\">If you have any questions we can help answer, please respond to this email!</p>
              <p style=\"font-size:16px; margin:24px 0 8px;\">Thanks,</p>
              <p style=\"font-size:16px; margin:8px 0;\">EkoLinq Support Team</p>
              <p style=\"font-size:16px; margin:8px 0;\">(866) 346-4765</p>
              <p style=\"font-size:16px; margin:16px 0 8px;\"><a href=\"mailto:contact@ekolinq.com\" style=\"color:#007bff; text-decoration:none;\">contact@ekolinq.com</a></p>
              <p style=\"font-size:16px; margin:8px 0;\"><a href=\"https://ekolinq.com\" style=\"color:#007bff; text-decoration:none;\">www.ekolinq.com</a></p>
            </div>
          </body>
        </html>
        """

        # ---------------------------------------------------------------------------
        # Send & Return -------------------------------------------------------------
        # ---------------------------------------------------------------------------
        mail.send(msg)
        return True

    except Exception as exc:
        print(f"Error while sending email: {exc}")
        return False



def send_edited_request_email(pickup):
    """
    Sends an email using your IONOS configuration (Flask-Mail).
    Returns True if successful, False if an error occurred.
    """
    try:
        mail = current_app.extensions.get('mail')

        first_name = pickup.fname
        request_id = pickup.request_id
        if pickup.address2: 
            address_formatted = f"{pickup.address} {pickup.address2}, {pickup.city}, CA {pickup.zipcode}"
        else:
            address_formatted = f"{pickup.address}, {pickup.city}, CA {pickup.zipcode}"

        try:
            dt = datetime.strptime(pickup.request_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%A, %b. %d")
        except Exception:
            formatted_date = pickup.request_date

        formatted_date_time = f"{formatted_date} between 8am-4pm"

        subject = f"EkoLinq: Updated Request Info For {formatted_date}"
        recipients = [pickup.email]
        msg = Message(
            subject,
            sender=current_app.config["MAIL_USERNAME"],
            recipients=recipients,
            bcc=["seanpvanderaa@gmail.com", current_app.config["MAIL_USERNAME"]]
        )

        # Email-safe HTML with fallback font:
        msg.html = f"""<html>
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>Pick-up Request Confirmation</title>
          <!-- Attempt to load Public Sans from Google Fonts. Some email clients will block this. -->
          <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600&display=swap" rel="stylesheet" />
          <style>
            /* Fallback approach: specify Public Sans first, then a system sans-serif */
            body, p, h1, h2, h3, td, li, a {{
              font-family: 'Public Sans', Arial, sans-serif !important;
            }}
          </style>
        </head>
        <body style="margin:0;padding:24px 0;background-color:#a1caa0;color:#000;font-family:'Public Sans',Arial,sans-serif;">
          <div style="width:90%;max-width:600px;margin:30px auto;background:#fff;padding:20px 30px 32px;border:1px solid #ddd;border-radius:40px;">
            <div style="text-align:center;">
              <img src="https://i.imgur.com/g6QpslJ.png" alt="EkoLinq Logo" width="160" style="display:block;margin:36px auto 48px;" />
            </div>
            <h1 style="font-size:24px;margin-bottom:16px;">Update: A Change to Your Request Details</h1>
            <p style="font-size:18px;margin-top:36px;"><strong>Hello {first_name},</strong></p>
            <p style="font-size:16px;">We've just received an update to your pickup request. Below are your updated details:</p>
            <div style="background:#098223;color:#fff;padding:16px;border-radius:8px;margin:48px 0;">
              <p style="margin:12px 0 8px;font-size:14px;font-weight:200;">Request ID</p>
              <p style="margin:0;font-weight:500;font-size:16px;">{request_id}</p>
              <p style="margin:12px 0 8px;font-size:14px;font-weight:200;">Address</p>
              <p style="margin:0;font-weight:500;font-size:16px;">{address_formatted}</p>
              <p style="margin:12px 0 8px;font-size:14px;font-weight:200;">Date &amp; Time</p>
              <p style="margin:0;font-weight:500;font-size:16px;">{formatted_date_time}</p>
              <a href="https://ekolinq.com/edit-request" style="text-decoration:none;">
                <p style="margin-top:36px;border-radius:5px;padding:12px 16px;color:#000;background-color:#EAB308;width:120px;text-align:center;font-weight:500;font-size:16px;">Edit Details</p>
              </a>
            </div>
            <h3 style="margin-top:36px;font-size:20px;">Reminder: Here's what you can and can't give us</h3>
            <table style="width:100%;border-collapse:separate;" cellspacing="4">
              <tr>
                <td style="vertical-align:top;width:50%;">
                  <table style="width:100%;border:1px solid #c6c6c6;border-radius:10px;padding:10px;background:#fff;padding-bottom:24px;">
                    <tr>
                      <th style="font-size:20px;padding:10px;text-align:left;font-weight:bold;">
                        <span style="color:#098223;font-size:24px;margin-right:12px;vertical-align:middle;">&#10003;</span>
                        DO Accept
                      </th>
                    </tr>
                    <tr>
                      <td style="padding:10px;">
                        <ul style="padding-left:20px;margin:0;">
                          <li style="margin:8px 0;font-size:16px;">Pants, jeans, skirts, dresses, suits, shorts, shirts</li>
                          <li style="margin:8px 0;font-size:16px;">Coats, jackets, gloves, hats, scarves</li>
                          <li style="margin:8px 0;font-size:16px;">Shoes, boots, heels, sneakers, sandals, socks</li>
                          <li style="margin:8px 0;font-size:16px;">Bras, underwear, slips, camisoles, tights</li>
                          <li style="margin:8px 0;font-size:16px;">Handbags, belts, ties, headbands</li>
                          <li style="margin:8px 0;font-size:16px;">Towels, sheets, comforters, blankets, tablecloths</li>
                          <li style="margin:8px 0;font-size:16px;">Wallets, totes, backpacks, stuffed animals</li>
                        </ul>
                      </td>
                    </tr>
                  </table>
                </td>
                <td style="vertical-align:top;width:50%;">
                  <table style="width:100%;border:1px solid #c6c6c6;border-radius:10px;padding:10px;background:#fff;padding-bottom:24px;">
                    <tr>
                      <th style="font-size:20px;padding:10px;text-align:left;font-weight:bold;">
                        <span style="color:red;font-size:24px;margin-right:12px;vertical-align:middle;">&#10005;</span>
                        DON'T Accept
                      </th>
                    </tr>
                    <tr>
                      <td style="padding:10px;">
                        <ul style="padding-left:20px;margin:0;">
                          <li style="margin:8px 0;font-size:16px;">Textiles that are wet, moldy, or contaminated with chemicals</li>
                          <li style="margin:8px 0;font-size:16px;">Bio-hazardous waste</li>
                          <li style="margin:8px 0;font-size:16px;">Mattresses, furniture, or other similar oversized items</li>
                        </ul>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            <p style="font-size:16px;margin-top:36px;">If you have any questions we can help answer, please respond to this email!</p>
            <p style="font-size:16px;margin:24px 0 8px;">Thanks,</p>
            <p style="font-size:16px;margin:8px 0;">EkoLinq Support Team</p>
            <p style="font-size:16px;margin:8px 0;">(866) 346-4765</p>
            <p style="font-size:16px;margin:16px 0 8px;"><a href="mailto:contact@ekolinq.com" style="color:#007bff;text-decoration:none;">contact@ekolinq.com</a></p>
            <p style="font-size:16px;margin:8px 0;"><a href="https://ekolinq.com" style="color:#007bff;text-decoration:none;">www.ekolinq.com</a></p>
          </div>
        </body>
        </html>"""

        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error while sending email: {str(e)}")
        return False


def send_error_report(error_type, error_message, traceback_info, request_method, request_path, form_data, args_data, user_agent, remote_addr):
    """
    Sends an error report email with the provided error data.
    Returns True if successful, False if an error occurred.
    """
    try:
        mail = current_app.extensions.get('mail')
        dt = datetime.today()  # or datetime.now()
        formatted_date = dt.strftime("%A, %b. %d")

        subject = f"Error Occurred: {error_type}, {formatted_date}"
        # Replace with your actual email address.
        recipients = ["seanpvanderaa@gmail.com"]
        
        msg = Message(
            subject,
            sender=current_app.config["MAIL_USERNAME"],
            recipients=recipients
        )

        msg.html = f"""
        <html>
        <head>
            <meta charset="UTF-8" />
            <title>Error Report</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    width: 90%;
                    max-width: 600px;
                    margin: 30px auto;
                    background: #ffffff;
                    padding: 20px;
                    border: 1px solid #dddddd;
                    border-radius: 8px;
                }}
                h1 {{
                    font-size: 22px;
                    margin-bottom: 16px;
                    color: #d9534f;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.5;
                }}
                .detail {{
                    background-color: #f1f1f1;
                    padding: 10px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                    font-family: "Courier New", monospace;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Error Report</h1>
                <p><strong>Error Type:</strong> {error_type}</p>
                <p><strong>Error Message:</strong> {error_message}</p>
                <p><strong>Traceback Information:</strong></p>
                <div class="detail">{traceback_info}</div>
                <p><strong>Request Method:</strong> {request_method}</p>
                <p><strong>Request Path:</strong> {request_path}</p>
                <p><strong>Form Data:</strong></p>
                <div class="detail">{form_data}</div>
                <p><strong>Arguments Data:</strong></p>
                <div class="detail">{args_data}</div>
                <p><strong>User Agent:</strong> {user_agent}</p>
                <p><strong>Remote Address:</strong> {remote_addr}</p>
            </div>
        </body>
        </html>
        """

        # Send the email using your Flask-Mail configuration.
        mail.send(msg)
        return True
    except Exception as e:
        # In production, consider logging this error.
        print(f"Error while sending error email: {str(e)}")
        return False

def error_report():
    return

