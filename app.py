from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, g, Response
from flask_socketio import SocketIO, emit
import sqlite3
import os
import json
import math
import random
import requests
from datetime import datetime, timedelta
from utils.db_handler import init_db, get_db, close_db, get_db_context
from utils.notifications import send_alert, send_whatsapp_alert, send_manager_escalation
from config import SECRET_KEY, DATABASE
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = DATABASE

socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
with app.app_context():
    init_db()

@app.teardown_appcontext
def close_db_connection(exception):
    close_db(exception)

# ==================== HELPERS ====================
def get_priority(emergency_type):
    """Auto-tag priority based on emergency type."""
    critical = ['fire', 'smoke', 'earthquake']
    high = ['medical', 'flood', 'intruder']
    if emergency_type in critical:
        return 'critical'
    elif emergency_type in high:
        return 'high'
    return 'medium'

def format_duration(seconds):
    """Convert seconds to HH:MM:SS."""
    if not seconds or seconds <= 0:
        return '00:00:00'
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# ==================== HOME & LANDING ====================
@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/sos')
def sos_page():
    return render_template('index.html')

@app.route('/panic', methods=['POST'])
def panic_button():
    data = request.json
    user_location = data.get('location')
    user_name = data.get('name', 'Anonymous')
    room_number = data.get('room_number', 'Unknown')
    emergency_type = data.get('emergency_type', 'medical')
    floor_number = data.get('floor_number', 1)
    
    if not user_location:
        return jsonify({'error': 'Location required'}), 400
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO emergencies (name, location, status, timestamp, emergency_type, room_number, floor_number, escalation_level)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, 1)
        ''', (user_name, user_location, datetime.now(), emergency_type, room_number, floor_number))
        emergency_id = cursor.lastrowid
        
        cursor.execute('''INSERT INTO analytics (emergency_id, event_type, timestamp, data)
                          VALUES (?, 'triggered', ?, ?)''',
                       (emergency_id, datetime.now(), json.dumps({'type': emergency_type, 'location': user_location})))
        conn.commit()
    
    send_alert(user_name, user_location, emergency_id)
    
    # Start escalation timers
    socketio.start_background_task(escalation_timer, emergency_id)
    socketio.start_background_task(auto_escalation_60s, emergency_id, user_name, user_location)
    
    socketio.emit('new_emergency', {
        'id': emergency_id,
        'name': user_name,
        'location': user_location,
        'status': 'pending',
        'timestamp': datetime.now().isoformat(),
        'emergency_type': emergency_type,
        'room_number': room_number,
        'escalation_level': 1,
        'priority': get_priority(emergency_type)
    })
    
    # Activity log
    socketio.emit('activity_feed', {
        'message': f'🚨 Emergency #{emergency_id} triggered by {user_name} ({emergency_type})',
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': 'emergency'
    })
    
    return jsonify({'message': 'Alert sent! Help is on the way.', 'id': emergency_id})

# ==================== ESCALATION TIMERS ====================
def escalation_timer(emergency_id):
    import time
    time.sleep(30)
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT status, escalation_level FROM emergencies WHERE id = ?', (emergency_id,))
        row = cursor.fetchone()
        if row and row['status'] == 'pending' and row['escalation_level'] < 3:
            new_level = row['escalation_level'] + 1
            cursor.execute('UPDATE emergencies SET escalation_level = ? WHERE id = ?',
                          (new_level, emergency_id))
            conn.commit()
            
            socketio.emit('escalation_alert', {
                'id': emergency_id,
                'escalation_level': new_level,
                'message': f'ESCALATION LEVEL {new_level}: Emergency #{emergency_id} not acknowledged!'
            })

def auto_escalation_60s(emergency_id, name, location):
    """Auto-escalate after 60 seconds with manager SMS + blinking red."""
    import time
    time.sleep(60)
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM emergencies WHERE id = ?', (emergency_id,))
        row = cursor.fetchone()
        if row and row['status'] == 'pending':
            cursor.execute('UPDATE emergencies SET escalation_level = 3 WHERE id = ?', (emergency_id,))
            conn.commit()
            
            socketio.emit('critical_escalation', {
                'id': emergency_id,
                'message': f'CRITICAL: Emergency #{emergency_id} UNACKNOWLEDGED for 60+ seconds!',
                'blink': True
            })
            
            socketio.emit('activity_feed', {
                'message': f'⚠️ Emergency #{emergency_id} auto-escalated (60s timeout)',
                'time': datetime.now().strftime('%H:%M:%S'),
                'type': 'escalation'
            })
            
            send_manager_escalation(emergency_id, name, location, level=3)

# ==================== DASHBOARD ====================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM emergencies ORDER BY timestamp DESC')
        emergencies = cursor.fetchall()
        
        cursor.execute('SELECT COUNT(*) FROM emergencies')
        total_emergencies = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM emergencies WHERE status = "pending"')
        pending_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM emergencies WHERE status = "resolved"')
        resolved_count = cursor.fetchone()[0]
        
        cursor.execute('''SELECT AVG(
            CASE WHEN resolved_at IS NOT NULL AND timestamp IS NOT NULL
            THEN (julianday(resolved_at) - julianday(timestamp)) * 86400
            ELSE NULL END)
            FROM emergencies WHERE status = "resolved"''')
        avg_response_raw = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT * FROM resources ORDER BY floor_number')
        resources = cursor.fetchall()
        
        cursor.execute('SELECT * FROM staff ORDER BY role')
        staff_list = cursor.fetchall()
        
        # Get recent activity
        cursor.execute('''SELECT * FROM analytics ORDER BY timestamp DESC LIMIT 20''')
        activities = cursor.fetchall()
    
    # Add priority to emergencies
    emergencies_with_priority = []
    for e in emergencies:
        e_dict = dict(e)
        e_dict['priority'] = get_priority(e_dict.get('emergency_type', 'medical'))
        e_dict['response_time_formatted'] = format_duration(e_dict.get('response_time_seconds'))
        emergencies_with_priority.append(e_dict)
    
    return render_template('dashboard.html', 
                          emergencies=emergencies_with_priority,
                          total_emergencies=total_emergencies,
                          pending_count=pending_count,
                          resolved_count=resolved_count,
                          avg_response=format_duration(avg_response_raw),
                          avg_response_raw=round(avg_response_raw, 1),
                          resources=resources,
                          staff_list=staff_list,
                          activities=activities)

# ==================== ACTIVITY FEED API ====================
@app.route('/api/activity-feed')
def activity_feed():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM analytics ORDER BY timestamp DESC LIMIT 30')
        activities = []
        for row in cursor.fetchall():
            activities.append({
                'id': row['id'],
                'emergency_id': row['emergency_id'],
                'event_type': row['event_type'],
                'timestamp': row['timestamp'],
                'data': row['data']
            })
    return jsonify(activities)

# ==================== MAP DATA API ====================
@app.route('/api/map-data')
def map_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT e.id, e.name, e.location, e.room_number, e.status, e.emergency_type, r.x_position, r.y_position FROM emergencies e LEFT JOIN rooms r ON e.room_number = r.room_number ORDER BY e.timestamp DESC')
        pins = []
        for row in cursor.fetchall():
            pins.append({
                'id': row['id'],
                'name': row['name'],
                'location': row['location'],
                'room': row['room_number'],
                'status': row['status'],
                'type': row['emergency_type'],
                'priority': get_priority(row['emergency_type']),
                'lat': row['x_position'] or random.uniform(12.9, 13.0),
                'lng': row['y_position'] or random.uniform(77.5, 77.7)
            })
        
        cursor.execute('SELECT exit_name, x_position, y_position FROM exits')
        exits = [{'name': r['exit_name'], 'lat': r['x_position'], 'lng': r['y_position']} for r in cursor.fetchall()]
    
    return jsonify({'incidents': pins, 'exits': exits})

# ==================== WEATHER API ====================
@app.route('/api/weather')
def weather():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        api_key = os.environ.get('OPENWEATHER_API_KEY', 'demo')
        if api_key == 'demo':
            return jsonify({
                'temp': 28,
                'condition': 'Partly Cloudy',
                'humidity': 65,
                'wind': 12,
                'alert': None,
                'location': 'Hotel Location'
            })
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Bangalore&appid={api_key}&units=metric"
        r = requests.get(url, timeout=3)
        data = r.json()
        return jsonify({
            'temp': round(data['main']['temp']),
            'condition': data['weather'][0]['main'],
            'humidity': data['main']['humidity'],
            'wind': data['wind']['speed'],
            'alert': data['weather'][0]['description'] if 'weather' in data else None,
            'location': data.get('name', 'Hotel Location')
        })
    except:
        return jsonify({'temp': 28, 'condition': 'Partly Cloudy', 'humidity': 65, 'wind': 12, 'alert': None})

# ==================== EXPORT PDF ====================
@app.route('/api/export-report')
def export_report():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="RescuEase Incident Report")
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("<b>RescuEase Crisis Management Report</b>", styles['Title']))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM emergencies')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM emergencies WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM emergencies WHERE status = "resolved"')
        resolved = cursor.fetchone()[0]
        
        story.append(Paragraph(f"<b>Summary:</b> Total: {total} | Pending: {pending} | Resolved: {resolved}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        cursor.execute('SELECT * FROM emergencies ORDER BY timestamp DESC LIMIT 50')
        rows = cursor.fetchall()
        
        data = [['ID', 'Name', 'Type', 'Location', 'Status', 'Response Time']]
        for row in rows:
            rt = format_duration(row['response_time_seconds']) if row['response_time_seconds'] else 'N/A'
            data.append([
                str(row['id']), row['name'], row['emergency_type'], 
                row['location'], row['status'], rt
            ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTSIZE', (0,1), (-1,-1), 9),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename=RescuEase_Report.pdf'})

# ==================== BROADCAST TO ALL GUESTS ====================
@app.route('/api/broadcast', methods=['POST'])
def broadcast_message():
    if 'user_id' not in session or session.get('user_role') not in ['admin', 'manager']:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    message = data.get('message', '')
    msg_type = data.get('type', 'info')
    
    socketio.emit('guest_broadcast', {
        'message': message,
        'type': msg_type,
        'timestamp': datetime.now().isoformat(),
        'from': session.get('user_id')
    })
    
    return jsonify({'message': 'Broadcast sent to all guests'})

# ==================== STAFF STATUS UPDATE ====================
@app.route('/api/staff/<username>/status', methods=['POST'])
def update_staff_status(username):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    status = data.get('status', 'available')
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE staff SET staff_status = ? WHERE username = ?', (status, username))
        conn.commit()
    socketio.emit('staff_status_update', {'username': username, 'status': status})
    return jsonify({'message': 'Staff status updated'})

# ==================== AI CAMERA FEED ====================
@app.route('/camera-feeds')
def camera_feeds_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('camera_feeds.html')

@app.route('/api/camera-feeds')
def camera_feeds():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    feeds = [
        {'id': 1, 'name': 'Lobby Camera', 'zone': 'Lobby', 'status': 'online', 'last_detection': None},
        {'id': 2, 'name': 'Kitchen Camera', 'zone': 'Kitchen', 'status': 'online', 'last_detection': None},
        {'id': 3, 'name': 'Hallway A', 'zone': 'Floor 1 Hallway', 'status': 'online', 'last_detection': 'smoke'},
        {'id': 4, 'name': 'Parking', 'zone': 'Basement Parking', 'status': 'online', 'last_detection': None},
    ]
    return jsonify({'feeds': feeds})

# ==================== TRACK / STATUS ====================
@app.route('/status/<int:emergency_id>')
@app.route('/track/<int:emergency_id>')
def status(emergency_id):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM emergencies WHERE id = ?', (emergency_id,))
        emergency = cursor.fetchone()
    if emergency:
        return render_template('track.html', emergency=emergency)
    return 'Emergency not found', 404

# ==================== EVACUATION MAP ====================
@app.route('/evacuation/<room_number>')
def evacuation(room_number):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rooms WHERE room_number = ?', (room_number,))
        room = cursor.fetchone()
        
        cursor.execute('SELECT * FROM exits WHERE status = "open" ORDER BY floor_number')
        exits = cursor.fetchall()
    
    if not room:
        return 'Room not found', 404
    
    nearest_exit = None
    min_distance = float('inf')
    for exit in exits:
        if exit['floor_number'] == room['floor_number']:
            dist = math.sqrt((exit['x_position'] - room['x_position'])**2 + 
                           (exit['y_position'] - room['y_position'])**2)
            if dist < min_distance:
                min_distance = dist
                nearest_exit = exit
    
    return render_template('evacuation.html', room=room, exits=exits, nearest_exit=nearest_exit)

# ==================== INCIDENT LOG / ANALYTICS ====================
@app.route('/incident-log')
def incident_log():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    date_filter = request.args.get('date', '')
    type_filter = request.args.get('type', '')
    status_filter = request.args.get('status', '')
    
    query = 'SELECT * FROM emergencies WHERE 1=1'
    params = []
    
    if date_filter:
        query += ' AND date(timestamp) = ?'
        params.append(date_filter)
    if type_filter:
        query += ' AND emergency_type = ?'
        params.append(type_filter)
    if status_filter:
        query += ' AND status = ?'
        params.append(status_filter)
    
    query += ' ORDER BY timestamp DESC'
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        emergencies = cursor.fetchall()
        
        cursor.execute('SELECT DISTINCT emergency_type FROM emergencies')
        types = [row['emergency_type'] for row in cursor.fetchall()]
    
    return render_template('incident_log.html', emergencies=emergencies, types=types,
                          date_filter=date_filter, type_filter=type_filter, status_filter=status_filter)

# ==================== RESOURCES ====================
@app.route('/resources')
def resources():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM resources ORDER BY floor_number, resource_type')
        resources = cursor.fetchall()
        
        cursor.execute('SELECT username, name, role, staff_status FROM staff WHERE is_active = 1 ORDER BY role')
        staff_list = cursor.fetchall()
    return render_template('resources.html', resources=resources, staff_list=staff_list)

@app.route('/api/resources/<int:resource_id>/update', methods=['POST'])
def update_resource(resource_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    status = data.get('status')
    quantity = data.get('quantity')
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE resources SET status = ?, quantity = ?, last_checked = ? WHERE id = ?',
                      (status, quantity, datetime.now(), resource_id))
        conn.commit()
    return jsonify({'message': 'Resource updated'})

# ==================== CONTACTS ====================
@app.route('/contacts')
def contacts():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM contacts ORDER BY priority, contact_type')
        contacts = cursor.fetchall()
    return render_template('contacts.html', contacts=contacts)

# ==================== PRIORITY ESCALATION ====================
@app.route('/priority-escalation')
def priority_escalation():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM emergencies WHERE status != 'resolved' 
                          ORDER BY escalation_level DESC, timestamp DESC''')
        active_emergencies = cursor.fetchall()
    
    return render_template('priority_escalation.html', emergencies=active_emergencies)

# ==================== STAFF PROFILE ====================
@app.route('/staff/profile')
def staff_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM staff WHERE username = ?', (session['user_id'],))
        staff = cursor.fetchone()
        
        cursor.execute('SELECT * FROM emergencies WHERE assigned_staff = ? ORDER BY timestamp DESC',
                      (session['user_id'],))
        assigned_emergencies = cursor.fetchall()
    return render_template('staff_profile.html', staff=staff, assigned_emergencies=assigned_emergencies)

# ==================== LOGIN / LOGOUT ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM staff WHERE username = ? AND password = ? AND is_active = 1',
                          (username, password))
            user = cursor.fetchone()
        
        if user:
            session['user_id'] = username
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== UPDATE STATUS WITH ESCALATION ====================
@app.route('/update_status/<int:emergency_id>', methods=['POST'])
def update_status(emergency_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    status = data.get('status')
    note = data.get('note', '')
    assigned_staff = data.get('assigned_staff', session.get('user_id'))
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT status_history, acknowledged_at, resolved_at FROM emergencies WHERE id = ?', (emergency_id,))
        row = cursor.fetchone()
        history_list = json.loads(row['status_history']) if row and row['status_history'] else []
        
        history_list.append({
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'note': note,
            'updated_by': session.get('user_id')
        })
        
        # Calculate response time
        response_time = None
        if status == 'in-progress' and row and not row['acknowledged_at']:
            cursor.execute('SELECT timestamp FROM emergencies WHERE id = ?', (emergency_id,))
            trigger_time = cursor.fetchone()['timestamp']
            response_time = int((datetime.now() - datetime.fromisoformat(str(trigger_time))).total_seconds())
        
        update_fields = 'status = ?, status_history = ?, assigned_staff = ?'
        params = [status, json.dumps(history_list), assigned_staff]
        
        if status == 'in-progress' and not row['acknowledged_at']:
            update_fields += ', acknowledged_at = ?'
            params.append(datetime.now())
        if status == 'resolved' and not row['resolved_at']:
            update_fields += ', resolved_at = ?'
            params.append(datetime.now())
        if response_time:
            update_fields += ', response_time_seconds = ?'
            params.append(response_time)
        
        params.append(emergency_id)
        cursor.execute(f'UPDATE emergencies SET {update_fields} WHERE id = ?', params)
        conn.commit()
    
    socketio.emit('track_update', {
        'id': emergency_id,
        'status': status,
        'history': history_list,
        'assigned_staff': assigned_staff
    })
    
    # Activity log
    socketio.emit('activity_feed', {
        'message': f'✅ Emergency #{emergency_id} updated to {status} by {session.get("user_id")}',
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': 'update'
    })
    
    return jsonify({'message': 'Status updated with tracking'})

# ==================== ACKNOWLEDGE API ====================
@app.route('/api/acknowledge/<int:emergency_id>', methods=['POST'])
def acknowledge_emergency(emergency_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE emergencies SET acknowledged_at = ?, assigned_staff = ? WHERE id = ?',
                      (datetime.now(), session['user_id'], emergency_id))
        conn.commit()
    
    socketio.emit('acknowledged', {'id': emergency_id, 'staff': session['user_id']})
    
    # Activity log
    socketio.emit('activity_feed', {
        'message': f'👤 Emergency #{emergency_id} acknowledged by {session.get("user_id")}',
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': 'acknowledge'
    })
    
    return jsonify({'message': 'Emergency acknowledged'})

# ==================== AI THREAT DETECTION (SIMULATION) ====================
@app.route('/api/ai-detect', methods=['POST'])
def ai_detect():
    data = request.json
    threat_types = ['smoke', 'fire', 'flood', 'earthquake', 'intruder']
    detected = data.get('sensor_data', '')
    
    # Simulated AI detection
    confidence = random.uniform(0.7, 0.99)
    threat_type = random.choice(threat_types)
    
    if confidence > 0.85:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO emergencies (name, location, status, timestamp, emergency_type)
                              VALUES (?, ?, 'pending', ?, ?)''',
                          (f'AI-{threat_type.upper()}', 'Camera Zone A', datetime.now(), threat_type))
            emergency_id = cursor.lastrowid
            conn.commit()
        
        socketio.emit('new_emergency', {
            'id': emergency_id,
            'name': f'AI-{threat_type.upper()}',
            'location': 'Camera Zone A',
            'status': 'pending',
            'timestamp': datetime.now().isoformat(),
            'emergency_type': threat_type,
            'ai_confidence': round(confidence, 2),
            'priority': get_priority(threat_type)
        })
        
        return jsonify({'threat_detected': True, 'type': threat_type, 'confidence': round(confidence, 2), 'emergency_id': emergency_id})
    
    return jsonify({'threat_detected': False, 'confidence': round(confidence, 2)})

# ==================== PRIORITY ESCALATION ====================
@app.route('/api/escalate', methods=['POST'])
def escalate_emergency():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    emergency_id = data.get('emergency_id')
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        # Get current emergency
        cursor.execute('SELECT * FROM emergencies WHERE id = ?', (emergency_id,))
        emergency = cursor.fetchone()
        if not emergency:
            return jsonify({'error': 'Emergency not found'}), 404
        
        # Increment escalation level (max 3)
        new_level = min(emergency['escalation_level'] + 1, 3)
        
        # Get staff by escalation level to notify
        cursor.execute('SELECT phone, email FROM staff WHERE escalation_level >= ? AND is_active = 1',
                      (new_level,))
        escalation_staff = cursor.fetchall()
        
        # Update emergency escalation level
        cursor.execute('''UPDATE emergencies SET escalation_level = ?, 
                          status = 'escalated' WHERE id = ?''',
                      (new_level, emergency_id))
        conn.commit()
    
    # Send escalation alerts
    send_manager_escalation(emergency_id, emergency['name'], emergency['location'], new_level)
    
    # Emit socket event
    socketio.emit('escalation', {
        'emergency_id': emergency_id,
        'old_level': emergency['escalation_level'],
        'new_level': new_level,
        'escalated_by': session.get('user_id'),
        'timestamp': datetime.now().isoformat()
    })
    
    # Activity log
    socketio.emit('activity_feed', {
        'message': f'🔴 Emergency #{emergency_id} ESCALATED to Level {new_level} by {session.get("user_id")}',
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': 'escalation'
    })
    
    return jsonify({
        'message': 'Emergency escalated',
        'new_level': new_level,
        'staff_notified': len(escalation_staff)
    })

# ==================== OFFLINE SYNC ====================
@app.route('/api/offline-sync', methods=['POST'])
def offline_sync():
    data = request.json
    action = data.get('action')
    payload = data.get('payload')
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO offline_queue (action, payload, synced) VALUES (?, ?, 0)',
                      (action, json.dumps(payload)))
        queue_id = cursor.lastrowid
        conn.commit()
    
    return jsonify({'queued': True, 'queue_id': queue_id})

@app.route('/api/offline-sync/process', methods=['POST'])
def process_offline_queue():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM offline_queue WHERE synced = 0 ORDER BY created_at')
        queue_items = cursor.fetchall()
        
        processed = 0
        for item in queue_items:
            payload = json.loads(item['payload'])
            if item['action'] == 'panic':
                cursor.execute('''INSERT INTO emergencies (name, location, status, timestamp)
                                  VALUES (?, ?, 'pending', ?)''',
                              (payload.get('name', 'Anonymous'), payload.get('location'), payload.get('timestamp', datetime.now())))
            processed += 1
        
        cursor.execute('UPDATE offline_queue SET synced = 1 WHERE synced = 0')
        conn.commit()
    
    return jsonify({'processed': processed})

# ==================== WHATSAPP ALERT ====================
@app.route('/api/whatsapp-alert/<int:emergency_id>', methods=['POST'])
def whatsapp_alert(emergency_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM emergencies WHERE id = ?', (emergency_id,))
        emergency = cursor.fetchone()
    
    if emergency:
        send_whatsapp_alert(emergency['name'], emergency['location'], emergency_id)
        return jsonify({'message': 'WhatsApp alert sent'})
    return jsonify({'error': 'Emergency not found'}), 404

# ==================== ANALYTICS API ====================
@app.route('/api/analytics')
def analytics():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT emergency_type, COUNT(*) FROM emergencies GROUP BY emergency_type')
        type_counts = {row['emergency_type']: row[1] for row in cursor.fetchall()}

        cursor.execute('''SELECT date(timestamp), COUNT(*) FROM emergencies
                          GROUP BY date(timestamp) ORDER BY date(timestamp) DESC LIMIT 7''')
        daily_counts = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]

        cursor.execute('SELECT AVG(response_time_seconds) FROM emergencies WHERE response_time_seconds IS NOT NULL')
        avg_time = cursor.fetchone()[0] or 0
    
    return jsonify({
        'type_counts': type_counts,
        'daily_counts': daily_counts,
        'avg_response_time': round(avg_time, 1)
    })

# ==================== GUEST PORTAL ====================
@app.route('/guest/login', methods=['GET', 'POST'])
def guest_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM guest_approvals WHERE username = ? AND password = ? AND status = "approved"',
                          (username, password))
            guest = cursor.fetchone()
        
        if guest:
            session['guest_id'] = guest['id']
            session['guest_name'] = guest['name']
            session['guest_username'] = guest['username']
            session['guest_room'] = guest['room_number']
            return redirect(url_for('guest_dashboard'))
        flash('Invalid credentials or account not yet approved')
    return render_template('guest_login.html')

@app.route('/guest/register', methods=['GET', 'POST'])
def guest_register():
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        room_number = request.form.get('room_number', '')
        request_reason = request.form.get('request_reason', '')
        
        try:
            with get_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO guest_approvals (username, password, name, email, phone, room_number, request_reason)
                                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
                              (username, password, name, email, phone, room_number, request_reason))
                conn.commit()
            return render_template('guest_login.html', request_sent=True)
        except sqlite3.IntegrityError:
            flash('Username already exists')
            return render_template('guest_register.html')
    return render_template('guest_register.html')

@app.route('/guest/dashboard')
def guest_dashboard():
    if 'guest_id' not in session:
        return redirect(url_for('guest_login'))
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM guest_approvals WHERE id = ?', (session['guest_id'],))
        guest = cursor.fetchone()
        
        if not guest:
            return redirect(url_for('guest_login'))
        
        cursor.execute('SELECT * FROM emergencies WHERE room_number = ? ORDER BY timestamp DESC',
                      (guest['room_number'],))
        emergencies = cursor.fetchall()
    
    return render_template('guest_dashboard.html', guest=guest, emergencies=emergencies)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='127.0.0.1', port=5000)
