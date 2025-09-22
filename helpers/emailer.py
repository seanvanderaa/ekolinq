# send_email.py
from flask_mail import Message
from flask import current_app  # helpful if you’re using the application factory pattern
from extensions import mail   # <--- no more "from app import mail"
from datetime import datetime
from markupsafe import escape
import os

def _unique_nonempty(sequence):
    seen = set()
    ordered = []
    for item in sequence:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered

def send_contact_email(name, email, message):
    """
    Sends a confirmation email to the customer and the admins (in the To line),
    and BCCs MAIL_ERROR_ADDRESS for monitoring.
    Returns True if successful, False otherwise.
    """
    try:
        config_name = os.getenv("FLASK_CONFIG", "development")
        subject = "[TESTING] EkoLinq: We received your message!" if config_name == "development" else "EkoLinq: We received your message!"

        # Admin identities
        admin_primary = current_app.config.get("MAIL_USERNAME", "")

        # Silent monitor / catch-all (BCC only)
        error_monitor = os.getenv("MAIL_ERROR_ADDRESS", "")

        # Build recipient lists
        to_recipients = _unique_nonempty([
            email,            # customer
            admin_primary,    # primary admin
        ])

        bcc_recipients = _unique_nonempty([
            error_monitor
        ])

        msg = Message(
            subject=subject,
            sender=admin_primary,         # comes from admin
            recipients=to_recipients,     # user + admins in-thread
            bcc=bcc_recipients            # MAIL_ERROR_ADDRESS for visibility
        )

        # Safely escape user-provided content for HTML
        name_html = escape(name)
        name_new = ", " + name_html
        message_html = escape(message)

        # Plain-text fallback
        msg.body = (
            f"Thanks for your message{name_new}! We've received it and will follow up with you shortly.\n\n"
            "Here's what you said:\n\n"
            f"{message_html}"
        )

        # HTML body (matches your house style)
        msg.html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>We Received Your Message</title>
  <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    body,p,h1,h2,h3,td,li,a{{font-family:'Public Sans',Arial,sans-serif!important;}}
    @media (prefers-color-scheme: dark) {{
      .bg-body{{background:#104378!important;}}
      .bg-card{{background:#ffffff!important;}}
      .bg-green{{background:#0c6a28!important;}}
      .text-dark{{color:#ffffff!important;}}
      a{{color:#8ac8ff!important;}}
    }}
    [data-ogsc] .bg-body{{background:#104378!important;}}
    [data-ogsc] .bg-card{{background:#ffffff!important;}}
    [data-ogsc] .bg-green{{background:#0c6a28!important;}}
    [data-ogsc] .text-dark{{color:#ffffff!important;}}
    [data-ogsc] a{{color:#8ac8ff!important;}}
    @media only screen and (max-width:600px){{
      .stack-col{{display:block!important;width:100%!important;max-width:100%!important;}}
      .stack-col > table{{width:100%!important;}}
    }}
    [data-ogsc] .stack-col,[data-ogsc] .stack-col > table{{display:block!important;width:100%!important;max-width:100%!important;}}
  </style>
</head>
<body bgcolor="#104378" class="bg-body" style="margin:0;padding:20px 0px;background-color:#104378;">
  <table role="presentation" width="100%" bgcolor="#104378" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:24px 0;">
        <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">
          <tr>
            <td bgcolor="#ffffff" class="bg-card" style="border:1px solid #ddd;border-radius:40px;padding:30px;">
              <table role="presentation" width="100%">
                <tr>
                  <td align="center" style="padding:0 0 24px 0;">
                    <img src="https://i.imgur.com/g6QpslJ.png" alt="EkoLinq Logo" width="140" style="display:block;height:auto;border:0;">
                  </td>
                </tr>
              </table>
              <h1 style="font-size:20px;line-height:1.4;margin:0 0 24px;font-weight:500;text-align:center;">We Received Your Message</h1>
              <p style="font-size:18px;line-height:1.5;margin:0 0 16px;">Thanks for your message{name_new}! We've received it and will follow up with you shortly.</p>
              <h3 style="margin:24px 0 12px;font-size:18px;">Your message:</h3>
              <table role="presentation" width="100%" style="border:none;border-radius:10px;background:#055d18;">
                <tr>
                  <td style="padding:24px;">
                    <p style="margin:0;font-size:16px;line-height:1.6;white-space:pre-wrap;color:white;">{message_html}</p>
                  </td>
                </tr>
              </table>
              <p style="font-size:16px;line-height:1.5;margin:32px 0 0;">If you have any additional details to share, simply reply to this email.</p>
              <p style="font-size:16px;margin:24px 0 8px;">Thanks,</p>
              <p style="font-size:16px;margin:8px 0;">EkoLinq Support Team</p>
              <p style="font-size:16px;margin:8px 0;">(866)&nbsp;346-4765</p>
              <p style="font-size:16px;margin:16px 0 8px;"><a href="mailto:contact@ekolinq.com" style="color:#007bff;text-decoration:none;">contact@ekolinq.com</a></p>
              <p style="font-size:16px;margin:8px 0;"><a href="https://ekolinq.com" style="color:#007bff;text-decoration:none;">www.ekolinq.com</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error while sending confirmation email: {str(e)}")
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

        SITE_URL = os.getenv("SITE_URL")

        edit_request_url = SITE_URL + '/edit-request-init'

        # ---------------------------------------------------------------------------
        # Subject & Recipients
        # ---------------------------------------------------------------------------
        subject = f"EkoLinq: Pickup Confirmation for {formatted_date}"
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
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1.0">
          <meta name="color-scheme" content="light dark">
          <meta name="supported-color-schemes" content="light dark">
          <title>Confirmation of Your Pickup</title>
          <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">

          <style>
            /* ---------- Base typography ---------- */
            body,p,h1,h2,h3,td,li,a{{
              font-family:'Public Sans',Arial,sans-serif!important;
            }}

            /* ---------- Dark-mode overrides (iOS, Apple Mail, Outlook.com) ---------- */
            @media (prefers-color-scheme: dark) {{
              .bg-body   {{background:#104378!important;}}
              .bg-card   {{background:#ffffff!important;}}
              .bg-green  {{background:#0c6a28!important;}}
              .text-dark {{color:#ffffff!important;}}
              a          {{color:#8ac8ff!important;}}
            }}

            /* ---------- Dark-mode overrides (Gmail / Outlook on Android) ---------- */
            [data-ogsc] .bg-body  {{background:#104378!important;}}
            [data-ogsc] .bg-card  {{background:#ffffff!important;}}
            [data-ogsc] .bg-green {{background:#0c6a28!important;}}
            [data-ogsc] .text-dark{{color:#ffffff!important;}}
            [data-ogsc] a         {{color:#8ac8ff!important;}}
            
            @media only screen and (max-width:600px){{
              .stack-col      {{display:block!important;width:100%!important;max-width:100%!important;}}
              .stack-col > table{{width:100%!important;}}
            }}

            /* Gmail / Outlook on Android */
            [data-ogsc] .stack-col,
            [data-ogsc] .stack-col > table{{
              display:block!important;width:100%!important;max-width:100%!important;
            }}
          </style>
        </head>

        <body bgcolor="#104378" class="bg-body" style="margin:0;padding:0;background-color:#104378;">
          <!-- Full-width wrapper -->
          <table role="presentation" width="100%" bgcolor="#104378" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center" style="padding:24px 0;">
                <!-- Constrained column -->
                <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#ffffff" class="bg-card" style="border:1px solid #ddd;border-radius:40px;padding:30px;">
                      <!-- ---------- Logo ---------- -->
                      <table role="presentation" width="100%">
                        <tr>
                          <td align="center" style="padding:0 0 24px 0;">
                            <img src="https://i.imgur.com/g6QpslJ.png" alt="EkoLinq Logo" width="140" style="display:block;height:auto;border:0;">
                          </td>
                        </tr>
                      </table>

                      <h1 style="font-size:20px;line-height:1.4;margin:0 0 24px;font-weight:500;text-align:center;">
                        Textile Pickup Confirmation
                      </h1>

                      {gated_notice_html}

                      <p style="font-size:18px;line-height:1.5;margin:36px 0 16px;">Hello{first_name},</p>

                      <p style="font-size:16px;line-height:1.5;margin:0 0 24px;">
                        Thanks for sparing the landfill and giving your clothes and other textiles a second life. Below is the information for your pickup request.
                        <b>Please remember to have your items out by 8&nbsp;AM on the day of your pickup.</b>
                      </p>

                      <!-- ---------- Green info module ---------- -->
                      <table role="presentation" width="100%" bgcolor="#098223" class="bg-green" style="background:#098223;border-radius:8px;">
                        <tr>
                          <td style="padding:16px;color:#ffffff;" class="text-dark">
                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Pickup &nbsp;ID</p>
                            <p style="margin:0 0 16px;font-weight:500;font-size:16px;">{request_id}</p>

                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Address</p>
                            <p style="margin:0 0 16px;font-weight:500;font-size:16px; color: white; text-decoration: none;">{address_formatted}</p>

                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Date&nbsp;&amp;&nbsp;Time</p>
                            <p style="margin:0;font-weight:500;font-size:16px;">{formatted_date_time}</p>

                            <!-- Button -->
                            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0;">
                              <tr>
                                <td align="center" bgcolor="#EAB308" style="border-radius:5px;">
                                  <a href="{edit_request_url}"
                                    style="display:inline-block;padding:12px 16px;font-size:16px;font-weight:500;color:#000;text-decoration:none;">
                                    Edit Pickup Details
                                  </a>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>

                      <!-- ---------- Accept / Don’t Accept ---------- -->
                      <h3 style="margin:36px 0 16px;font-size:20px;">Reminder: Here's what you can and can't give us</h3>

                      <table role="presentation" width="100%">
                        <tr>
                          <!-- DO Accept -->
                          <td class="stack-col" width="50%" valign="top" style="padding-right:4px;">
                            <table role="presentation" width="100%" style="border:1px solid #c6c6c6;border-radius:10px;">
                              <tr>
                                <td style="padding:10px;">
                                  <h4 style="margin:0 0 8px;font-size:20px;font-weight:bold;">
                                    <span style="color:#098223;font-size:24px;vertical-align:middle;margin-right:6px;">&#10003;</span>
                                    DO&nbsp;Accept
                                  </h4>
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

                          <!-- DON'T Accept -->
                          <td class="stack-col" width="50%" valign="top" style="padding-left:4px;">
                            <table role="presentation" width="100%" style="border:1px solid #c6c6c6;border-radius:10px;">
                              <tr>
                                <td style="padding:10px;">
                                  <h4 style="margin:0 0 8px;font-size:20px;font-weight:bold;">
                                    <span style="color:#ff0000;font-size:24px;vertical-align:middle;margin-right:6px;">&#10005;</span>
                                    DON'T&nbsp;Accept
                                  </h4>
                                  <ul style="padding-left:20px;margin:0;">
                                    <li style="margin:8px 0;font-size:16px;">Textiles that are wet, moldy, or contaminated with chemicals</li>
                                    <li style="margin:8px 0;font-size:16px;">Bio-hazardous waste</li>
                                    <li style="margin:8px 0;font-size:16px;">Pillows and cushions</li>
                                    <li style="margin:8px 0;font-size:16px;">Mattresses, furniture, or other similar oversized items</li>
                                  </ul>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>

                      <!-- ---------- Footer ---------- -->
                      <p style="font-size:16px;line-height:1.5;margin:36px 0 0;">If you have any questions we can help answer, please respond to this email!</p>
                      <p style="font-size:16px;margin:24px 0 8px;">Thanks,</p>
                      <p style="font-size:16px;margin:8px 0;">EkoLinq Support Team</p>
                      <p style="font-size:16px;margin:8px 0;">(866)&nbsp;346-4765</p>
                      <p style="font-size:16px;margin:16px 0 8px;">
                        <a href="mailto:contact@ekolinq.com" style="color:#007bff;text-decoration:none;">contact@ekolinq.com</a>
                      </p>
                      <p style="font-size:16px;margin:8px 0;">
                        <a href="https://ekolinq.com" style="color:#007bff;text-decoration:none;">www.ekolinq.com</a>
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
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

        SITE_URL = os.getenv("SITE_URL")

        edit_request_url = SITE_URL + '/edit-request-init'

        subject = f"EkoLinq: Updated Pickup Request Info For {formatted_date}"
        recipients = [pickup.email]
        msg = Message(
            subject,
            sender=current_app.config["MAIL_USERNAME"],
            recipients=recipients,
            bcc=["seanpvanderaa@gmail.com"]
        )
        
        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1.0">
          <meta name="color-scheme" content="light dark">
          <meta name="supported-color-schemes" content="light dark">
          <title>Edited Pickup Request Confirmation</title>
          <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">

          <style>
            /* ---------- Base typography ---------- */
            body,p,h1,h2,h3,td,li,a{{
              font-family:'Public Sans',Arial,sans-serif!important;
            }}

            /* ---------- Dark-mode overrides (iOS, Apple Mail, Outlook.com) ---------- */
            @media (prefers-color-scheme: dark) {{
              .bg-body   {{background:#104378!important;}}
              .bg-card   {{background:#ffffff!important;}}
              .bg-green  {{background:#0c6a28!important;}}
              .text-dark {{color:#ffffff!important;}}
              a          {{color:#8ac8ff!important;}}
            }}

            /* ---------- Dark-mode overrides (Gmail / Outlook on Android) ---------- */
            [data-ogsc] .bg-body  {{background:#104378!important;}}
            [data-ogsc] .bg-card  {{background:#ffffff!important;}}
            [data-ogsc] .bg-green {{background:#0c6a28!important;}}
            [data-ogsc] .text-dark{{color:#ffffff!important;}}
            [data-ogsc] a         {{color:#8ac8ff!important;}}
            
            @media only screen and (max-width:600px){{
              .stack-col      {{display:block!important;width:100%!important;max-width:100%!important;}}
              .stack-col > table{{width:100%!important;}}
            }}

            /* Gmail / Outlook on Android */
            [data-ogsc] .stack-col,
            [data-ogsc] .stack-col > table{{
              display:block!important;width:100%!important;max-width:100%!important;
            }}
          </style>
        </head>

        <body bgcolor="#104378" class="bg-body" style="margin:0;padding:0;background-color:#104378;">
          <!-- Full-width wrapper -->
          <table role="presentation" width="100%" bgcolor="#104378" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center" style="padding:48px 0;">
                <!-- Constrained column -->
                <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#ffffff" class="bg-card" style="border:1px solid #ddd;border-radius:40px;padding:30px;">
                      <!-- ---------- Logo ---------- -->
                      <table role="presentation" width="100%">
                        <tr>
                          <td align="center" style="padding:0 0 24px 0;">
                            <img src="https://i.imgur.com/g6QpslJ.png" alt="EkoLinq Logo" width="140" style="display:block;height:auto;border:0;">
                          </td>
                        </tr>
                      </table>
                      <h1 style="font-size:24px;margin-bottom:16px;">Update: A Change to Your Pickup Details</h1>
                      <p style="font-size:18px;margin-top:36px;"><strong>Hello {first_name},</strong></p>
                      <p style="font-size:16px;">We've just received an update to your pickup request. Below are your updated details:</p>
                      <!-- ---------- Green info module ---------- -->
                      <table role="presentation" width="100%" bgcolor="#098223" class="bg-green" style="background:#098223;border-radius:8px;">
                        <tr>
                          <td style="padding:16px;color:#ffffff;" class="text-dark">
                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Pickup &nbsp;ID</p>
                            <p style="margin:0 0 16px;font-weight:500;font-size:16px;">{request_id}</p>

                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Address</p>
                            <p style="margin:0 0 16px;font-weight:500;font-size:16px; color: white; text-decoration: none;">{address_formatted}</p>

                            <p style="margin:0 0 8px;font-size:14px;font-weight:200;">Date&nbsp;&amp;&nbsp;Time</p>
                            <p style="margin:0;font-weight:500;font-size:16px;">{formatted_date_time}</p>

                            <!-- Button -->
                            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0;">
                              <tr>
                                <td align="center" bgcolor="#EAB308" style="border-radius:5px;">
                                  <a href="{edit_request_url}"
                                    style="display:inline-block;padding:12px 16px;font-size:16px;font-weight:500;color:#000;text-decoration:none;">
                                    Edit Pickup Details
                                  </a>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>

                      <!-- ---------- Accept / Don’t Accept ---------- -->
                      <h3 style="margin:36px 0 16px;font-size:20px;">Reminder: Here's what you can and can't give us</h3>

                      <table role="presentation" width="100%">
                        <tr>
                          <!-- DO Accept -->
                          <td class="stack-col" width="50%" valign="top" style="padding-right:4px;">
                            <table role="presentation" width="100%" style="border:1px solid #c6c6c6;border-radius:10px;">
                              <tr>
                                <td style="padding:10px;">
                                  <h4 style="margin:0 0 8px;font-size:20px;font-weight:bold;">
                                    <span style="color:#098223;font-size:24px;vertical-align:middle;margin-right:6px;">&#10003;</span>
                                    DO&nbsp;Accept
                                  </h4>
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

                          <!-- DON'T Accept -->
                          <td class="stack-col" width="50%" valign="top" style="padding-left:4px;">
                            <table role="presentation" width="100%" style="border:1px solid #c6c6c6;border-radius:10px;">
                              <tr>
                                <td style="padding:10px;">
                                  <h4 style="margin:0 0 8px;font-size:20px;font-weight:bold;">
                                    <span style="color:#ff0000;font-size:24px;vertical-align:middle;margin-right:6px;">&#10005;</span>
                                    DON'T&nbsp;Accept
                                  </h4>
                                  <ul style="padding-left:20px;margin:0;">
                                    <li style="margin:8px 0;font-size:16px;">Textiles that are wet, moldy, or contaminated with chemicals</li>
                                    <li style="margin:8px 0;font-size:16px;">Bio-hazardous waste</li>
                                    <li style="margin:8px 0;font-size:16px;">Pillows and cushions</li>
                                    <li style="margin:8px 0;font-size:16px;">Mattresses, furniture, or other similar oversized items</li>
                                  </ul>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>

                      <!-- ---------- Footer ---------- -->
                      <p style="font-size:16px;line-height:1.5;margin:36px 0 0;">If you have any questions we can help answer, please respond to this email!</p>
                      <p style="font-size:16px;margin:24px 0 8px;">Thanks,</p>
                      <p style="font-size:16px;margin:8px 0;">EkoLinq Support Team</p>
                      <p style="font-size:16px;margin:8px 0;">(866)&nbsp;346-4765</p>
                      <p style="font-size:16px;margin:16px 0 8px;">
                        <a href="mailto:contact@ekolinq.com" style="color:#007bff;text-decoration:none;">contact@ekolinq.com</a>
                      </p>
                      <p style="font-size:16px;margin:8px 0;">
                        <a href="https://ekolinq.com" style="color:#007bff;text-decoration:none;">www.ekolinq.com</a>
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
        """


        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error while sending email: {str(e)}")
        return False



def send_cancellation_email(pickup):
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

        try:
            dt = datetime.strptime(pickup.request_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%A, %b. %d")
        except Exception:
            formatted_date = pickup.request_date

        formatted_date_time = f"{formatted_date}"

        SITE_URL = os.getenv("SITE_URL")

        # ---------------------------------------------------------------------------
        # Subject & Recipients
        # ---------------------------------------------------------------------------
        subject = f"EkoLinq: Pickup Request Cancelled for {formatted_date}"
        recipients = [pickup.email]
        msg = Message(
            subject=subject,
            sender=current_app.config["MAIL_USERNAME"],
            recipients=recipients,
            bcc=[current_app.config["MAIL_USERNAME"]],
        )

        # ---------------------------------------------------------------------------
        # Compose the HTML body
        # ---------------------------------------------------------------------------
        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1.0">
          <meta name="color-scheme" content="light dark">
          <meta name="supported-color-schemes" content="light dark">
          <title>Pickup Cancellation Confirmation</title>
          <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">

          <style>
            /* ---------- Base typography ---------- */
            body,p,h1,h2,h3,td,li,a{{
              font-family:'Public Sans',Arial,sans-serif!important;
            }}

            /* ---------- Dark-mode overrides (iOS, Apple Mail, Outlook.com) ---------- */
            @media (prefers-color-scheme: dark) {{
              .bg-body   {{background:#098223!important;}}
              .bg-card   {{background:#ffffff!important;}}
              .bg-green  {{background:#0c6a28!important;}}
              .text-dark {{color:#ffffff!important;}}
              a          {{color:#8ac8ff!important;}}
            }}

            /* ---------- Dark-mode overrides (Gmail / Outlook on Android) ---------- */
            [data-ogsc] .bg-body  {{background:#098223!important;}}
            [data-ogsc] .bg-card  {{background:#ffffff!important;}}
            [data-ogsc] .bg-green {{background:#0c6a28!important;}}
            [data-ogsc] .text-dark{{color:#ffffff!important;}}
            [data-ogsc] a         {{color:#8ac8ff!important;}}
            
            @media only screen and (max-width:600px){{
              .stack-col      {{display:block!important;width:100%!important;max-width:100%!important;}}
              .stack-col > table{{width:100%!important;}}
            }}

            /* Gmail / Outlook on Android */
            [data-ogsc] .stack-col,
            [data-ogsc] .stack-col > table{{
              display:block!important;width:100%!important;max-width:100%!important;
            }}
          </style>
        </head>

        <body bgcolor="#098223" class="bg-body" style="margin:0;padding:0;background-color:#098223;">
          <!-- Full-width wrapper -->
          <table role="presentation" width="100%" bgcolor="#098223" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center" style="padding:48px 0;">
                <!-- Constrained column -->
                <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#ffffff" class="bg-card" style="border:1px solid #ddd;border-radius:40px;padding:30px;">
                      <!-- ---------- Logo ---------- -->
                      <table role="presentation" width="100%">
                        <tr>
                          <td align="center" style="padding:16px 0 48px 0;">
                            <img src="https://i.imgur.com/g6QpslJ.png" alt="EkoLinq Logo" width="140" style="display:block;height:auto;border:0;">
                          </td>
                        </tr>
                      </table>

                      <h1 style="line-height:1.4;margin:0 0 24px;font-weight:500;text-align:left;">
                        Your pickup request has been cancelled.
                      </h1>

                      <p style="font-size:18px;line-height:1.5;margin:36px 0 16px;">Hello{first_name},</p>

                      <p style="font-size:16px;line-height:1.5;margin:0 0 24px;">
                        As per your request, we have cancelled your pickup request (ID: {request_id}) scheduled for <b>{formatted_date}</b>. If this was done in error, or if you did not cancel the request yourself, please respond to this email.
                      </p>

                      <p style="font-size:16px;line-height:1.5;margin:0 0 24px;">
                        If you would like to schedule a pickup in the future to help keep clothing and textiles out of the landfill, you can do so at any time at <a href="{SITE_URL}">ekolinq.com</a>. 
                      </p>

                      <p style="font-size:16px;line-height:1.5;margin:0 0 24px;">
                        Warm regards,
                      </p>
                      <p style="font-size:16px;line-height:1.5;margin:0 0 24px;">
                        The EkoLinq Team
                      </p>
                      <p style="font-size:16px;margin:8px 0;">(866)&nbsp;346-4765</p>
                      <p style="font-size:16px;margin:16px 0 8px;">
                        <a href="mailto:contact@ekolinq.com" style="color:#007bff;text-decoration:none;">contact@ekolinq.com</a>
                      </p>
                      <p style="font-size:16px;margin:8px 0;">
                        <a href="https://ekolinq.com" style="color:#007bff;text-decoration:none;">www.ekolinq.com</a>
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
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
                <p><strong>Request Method:</strong> {request_method}</p>
                <p><strong>Request Path:</strong> {request_path}</p>
                <p><strong>Form Data:</strong></p>
                <div class="detail">{form_data}</div>
                <p><strong>Arguments Data:</strong></p>
                <div class="detail">{args_data}</div>
                <p><strong>Error Type:</strong> {error_type}</p>
                <p><strong>Error Message:</strong> {error_message}</p>
                <p><strong>Traceback Information:</strong></p>
                <div class="detail">{traceback_info}</div>
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

def send_mopf_email(email, value, date):
    """
    Sends a confirmation email to the customer and the admins (in the To line),
    and BCCs MAIL_ERROR_ADDRESS for monitoring.
    Returns True if successful, False otherwise.
    """
    try:
        config_name = os.getenv("FLASK_CONFIG", "development")
        subject = "[TESTING] Muwekma Ohlone Preservation Foundation Donation Tax Receipt" if config_name == "development" else "Muwekma Ohlone Preservation Foundation Donation Tax Receipt"

        # Admin identities
        admin_primary = current_app.config.get("MAIL_USERNAME", "")

        # Silent monitor / catch-all (BCC only)
        error_monitor = os.getenv("MAIL_ERROR_ADDRESS", "")

        # Build recipient lists
        to_recipients = _unique_nonempty([
            email            # customer
        ])

        bcc_recipients = _unique_nonempty([
            admin_primary,    # primary admin
            error_monitor
        ])

        msg = Message(
            subject=subject,
            sender=admin_primary,         # comes from admin
            recipients=to_recipients,     # user + admins in-thread
            bcc=bcc_recipients            # MAIL_ERROR_ADDRESS for visibility
        )

        # HTML body (matches your house style)
        msg.html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>We Received Your Message</title>
  <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    body,p,h1,h2,h3,td,li,a{{font-family:'Public Sans',Arial,sans-serif!important;color:black;}}
    @media (prefers-color-scheme: dark) {{
      .bg-body{{background:#104378!important;}}
      .bg-card{{background:#ffffff!important;}}
      .bg-green{{background:#0c6a28!important;}}
      .text-dark{{color:#ffffff!important;}}
      a{{color:#8ac8ff!important;}}
    }}
    [data-ogsc] .bg-body{{background:#104378!important;}}
    [data-ogsc] .bg-card{{background:#ffffff!important;}}
    [data-ogsc] .bg-green{{background:#0c6a28!important;}}
    [data-ogsc] .text-dark{{color:#ffffff!important;}}
    [data-ogsc] a{{color:#8ac8ff!important;}}
    @media only screen and (max-width:600px){{
      .stack-col{{display:block!important;width:100%!important;max-width:100%!important;}}
      .stack-col > table{{width:100%!important;}}
    }}
    [data-ogsc] .stack-col,[data-ogsc] .stack-col > table{{display:block!important;width:100%!important;max-width:100%!important;}}
  </style>
</head>
<body bgcolor="#D4DECA" class="bg-body" style="margin:0;padding:20px 0px;background-color:#D4DECA;">
  <table role="presentation" width="100%" bgcolor="#D4DECA" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:24px 0;">
        <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">
          <tr>
            <td bgcolor="#ffffff" class="bg-card" style="border:1px solid #ddd;border-radius:40px;padding:30px;">
              <table role="presentation" width="100%">
                <tr>
                  <td align="center" style="padding:0 0 24px 0;">
                    <img src="https://www.ekolinq.com/static/images/mopf_logo_highres.png" alt="Muwekma Ohlone Preservation Foundation Logo" width="140" style="display:block;height:auto;border:0;background:white;">
                  </td>
                </tr>
              </table>
              <h3 style="font-size:18px;line-height:1.4;margin:0 0 12px;font-weight:300;text-align:center;color:black;">Thank you for your donation to the</h3>
              <h1 style="font-size:24px;line-height:1.4;margin:0 0 36px;font-weight:700;text-align:center;color:black;">Muwekma Ohlone Preservation Foundation</h1>
              <table role="presentation" width="100%" style="border:none;border-radius:10px;background:#055d18;">
                <tr>
                  <td style="padding:24px;">
                    <p style="margin:0 0 16px;font-weight:700;font-size:16px;color: white;">Here is a record of your tax-deductible donations. You can print this email for your records.</p>

                    <p style="margin:0 0 8px;font-size:14px;font-weight:200;color: white;">Date</p>
                    <p style="margin:0 0 16px;font-weight:500;font-size:16px;color: white;">{date}</p>

                    <p style="margin:0 0 8px;font-size:14px;font-weight:200;color: white;">Donated Items</p>
                    <p style="margin:0 0 16px;font-weight:500;font-size:16px; color: white; text-decoration: none;">Clothes, shoes, accessories, or other textile goods.</p>

                    <p style="margin:0 0 8px;font-size:14px;font-weight:200;color: white;">Estimated Value of Donated Items</p>
                    <p style="margin:0;font-weight:500;font-size:16px;color: white;">${value}</p>
                  </td>
                </tr>
              </table>
              <p style="font-size:16px;line-height:1.5;margin:32px 0 0;color:black;">The Muwekma Ohlone Preservation Foundation is a registered 501(c)(3) non-profit organization.</p>
              <p style="font-size:16px;margin:8px 0;color:black;">EIN Number:<br>88-0910186</p>
              <p style="font-size:16px;margin:8px 0;color:black;">Please direct questions and comments to:<br><a href="mailto:info@muwekmafoundation.org">info@muwekmafoundation.org</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error while sending confirmation email: {str(e)}")
        return False