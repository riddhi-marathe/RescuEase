import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from config import EMAIL_SERVER, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD, TWILIO_SID, TWILIO_TOKEN, TWILIO_PHONE
from datetime import datetime

def send_alert(name, location, emergency_id):
    """Send email and SMS alerts to emergency contacts."""
    
    # Email alert
    send_email_alert(name, location, emergency_id)
    
    # SMS alert (Twilio)
    send_sms_alert(name, location, emergency_id)
    
    print(f"🚨 Alerts sent for emergency {emergency_id}: {name} at {location}")

def send_manager_escalation(emergency_id, name, location, level=2):
    """Send escalation SMS to managers when pending too long."""
    try:
        from config import EMERGENCY_MANAGER_PHONE
        manager_phone = getattr(__import__('config'), 'EMERGENCY_MANAGER_PHONE', '+1234567890')
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        body = f"🚨 ESCALATION LEVEL {level}: Emergency #{emergency_id} at {location} for {name} has been pending for 60+ seconds. Respond immediately!"
        data = {'To': manager_phone, 'From': TWILIO_PHONE, 'Body': body}
        auth = (TWILIO_SID, TWILIO_TOKEN)
        response = requests.post(url, data=data, auth=auth)
        print(f"Manager escalation SMS sent: {response.status_code}")
    except Exception as e:
        print(f"Manager escalation failed: {e}")

def send_email_alert(name, location, emergency_id):
    """Send email notification."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = EMAIL_USERNAME  # Update with real emergency contacts
        msg['Subject'] = f"🚨 EMERGENCY ALERT #{emergency_id}"
        
        body = f"""
        EMERGENCY ALERT #{emergency_id}
        
        Name: {name}
        Location: {location}
        Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Status: Pending
        
        Please respond immediately!
        """
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Email alert failed: {e}")

def send_sms_alert(name, location, emergency_id):
    """Send SMS via Twilio."""
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        
        data = {
            'To': '+1234567890',  # Update with emergency contact
            'From': TWILIO_PHONE,
            'Body': f"🚨 EMERGENCY #{emergency_id}: {name} needs help at {location}"
        }
        
        auth = (TWILIO_SID, TWILIO_TOKEN)
        response = requests.post(url, data=data, auth=auth)
        
        if response.status_code != 201:
            print(f"SMS failed: {response.text}")
    except Exception as e:
        print(f"SMS alert failed: {e}")

def send_whatsapp_alert(name, location, emergency_id):
    """Send WhatsApp alert via Twilio."""
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        
        data = {
            'To': 'whatsapp:+1234567890',  # Update with emergency contact
            'From': f'whatsapp:{TWILIO_PHONE}',
            'Body': f"🚨 *CRISIS ALERT* #{emergency_id}\n\n*Name:* {name}\n*Location:* {location}\n*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n*Status:* Pending\n\nPlease respond immediately!"
        }
        
        auth = (TWILIO_SID, TWILIO_TOKEN)
        response = requests.post(url, data=data, auth=auth)
        
        if response.status_code != 201:
            print(f"WhatsApp failed: {response.text}")
        else:
            print(f"✅ WhatsApp alert sent for emergency {emergency_id}")
    except Exception as e:
        print(f"WhatsApp alert failed: {e}")
