from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, g
from flask_socketio import SocketIO, emit
import sqlite3
import os
import json
import math
import random
from datetime import datetime, timedelta
from utils.db_handler import init_db, get_db, close_db, get_db_context
from utils.notifications import send_alert, send_whatsapp_alert
from config import SECRET_KEY, DATABASE

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
        
        # Log analytics
        cursor.execute('''INSERT INTO analytics (emergency_id, event_type, timestamp, data)
                          VALUES (?, 'triggered', ?, ?)''',
                       (emergency_id, datetime.now(), json.dumps({'type': emergency_type, 'location': user_location})))
        conn.commit()
    
    # Send multi-channel alerts
    send_alert(user_name, user_location, emergency_id)
    
    # Start escalation timer (30 seconds)
    socketio.start_background_task(escalation_timer, emergency_id)
    
    socketio.emit('new_emergency', {
        'id': emergency_id,
        'name': user_name,
        'location': user_location,
        'status': 'pending',
        'timestamp': datetime.now().isoformat(),
        'emergency_type': emergency_type,
        'room_number': room_number,
        'escalation_level': 1
    })
    
    return jsonify({'message': 'Alert sent! Help is on the way.', 'id': emergency_id})

# ==================== ESCALATION TIMER ====================
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
        avg_response = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT * FROM resources ORDER BY floor_number')
        resources = cursor.fetchall()
    
    return render_template('dashboard.html', emergencies=emergencies, 
                          total_emergencies=total_emergencies,
                          pending_count=pending_count,
                          resolved_count=resolved_count,
                          avg_response=round(avg_response, 1),
                          resources=resources)

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
    
    # Calculate nearest exit
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
    return render_template('resources.html', resources=resources)

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
            'ai_confidence': round(confidence, 2)
        })
        
        return jsonify({'threat_detected': True, 'type': threat_type, 'confidence': round(confidence, 2), 'emergency_id': emergency_id})
    
    return jsonify({'threat_detected': False, 'confidence': round(confidence, 2)})

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
        
        cursor.execute('SELECT * FROM emergencies WHERE name = ? ORDER BY timestamp DESC',
                      (guest['name'],))
        my_emergencies = cursor.fetchall()
    
    return render_template('guest_dashboard.html', guest=guest, my_emergencies=my_emergencies)

@app.route('/guest/logout')
def guest_logout():
    session.pop('guest_id', None)
    session.pop('guest_name', None)
    session.pop('guest_username', None)
    session.pop('guest_room', None)
    return redirect(url_for('index'))

# ==================== ADMIN GUEST APPROVALS ====================
@app.route('/admin/approvals')
def admin_approvals():
    if 'user_id' not in session or session.get('user_role') not in ['admin', 'manager']:
        return redirect(url_for('login'))
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM guest_approvals ORDER BY requested_at DESC')
        approvals = cursor.fetchall()
        
        cursor.execute('SELECT COUNT(*) FROM guest_approvals WHERE status = "pending"')
        pending_approvals = cursor.fetchone()[0]
    
    return render_template('admin_approvals.html', approvals=approvals, pending_approvals=pending_approvals)

@app.route('/api/approve-guest/<int:guest_id>', methods=['POST'])
def approve_guest(guest_id):
    if 'user_id' not in session or session.get('user_role') not in ['admin', 'manager']:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE guest_approvals SET status = "approved", approved_by = ?, approved_at = ? WHERE id = ?',
                      (session['user_id'], datetime.now(), guest_id))
        conn.commit()
    
    socketio.emit('guest_approved', {'guest_id': guest_id, 'approved_by': session['user_id']})
    return jsonify({'message': 'Guest approved'})

@app.route('/api/reject-guest/<int:guest_id>', methods=['POST'])
def reject_guest(guest_id):
    if 'user_id' not in session or session.get('user_role') not in ['admin', 'manager']:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE guest_approvals SET status = "rejected", approved_by = ?, approved_at = ? WHERE id = ?',
                      (session['user_id'], datetime.now(), guest_id))
        conn.commit()
    
    return jsonify({'message': 'Guest rejected'})

# ==================== SOCKET.IO ====================
@socketio.on('connect')
def handle_connect():
    emit('connected', {'message': 'Connected to RescuEase Crisis Management'})

@socketio.on('join_track_room')
def join_track_room(data):
    room = f'emergency_{data}'
    from flask_socketio import join_room
    join_room(room)

if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n{'='*50}")
    print(f"  RescuEase Server Started")
    print(f"{'='*50}")
    print(f"  Local:     http://127.0.0.1:5000")
    print(f"  Network:   http://{local_ip}:5000")
    print(f"{'='*50}\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

