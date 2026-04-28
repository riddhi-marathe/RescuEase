import os

SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-rescuease-secret-key-change-in-production'
DATABASE = 'rescuease.db'

# Email/SMS config - update with real credentials
EMAIL_SERVER = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USERNAME = 'your-email@gmail.com'
EMAIL_PASSWORD = 'your-app-password'
TWILIO_SID = 'your-twilio-sid'
TWILIO_TOKEN = 'your-twilio-token'
TWILIO_PHONE = '+1234567890'
EMERGENCY_MANAGER_PHONE = os.environ.get('MANAGER_PHONE', '+1234567890')
