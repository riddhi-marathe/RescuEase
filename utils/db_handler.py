import sqlite3
from flask import g
from contextlib import contextmanager
from config import DATABASE
from datetime import datetime
import json

# Register adapter for Python 3.12+ compatibility
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())

def get_db():
    if not hasattr(g, '_database'):
        g._database = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g._database.row_factory = sqlite3.Row
    return g._database

@contextmanager
def get_db_context():
    db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

def init_db():
    with get_db_context() as db:
        # Main emergencies table
        db.execute('''CREATE TABLE IF NOT EXISTS emergencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            status TEXT DEFAULT 'pending',
            status_history TEXT DEFAULT '[]',
            emergency_type TEXT DEFAULT 'medical',
            room_number TEXT DEFAULT NULL,
            floor_number INTEGER DEFAULT 1,
            assigned_staff TEXT DEFAULT NULL,
            escalation_level INTEGER DEFAULT 1,
            acknowledged_at DATETIME DEFAULT NULL,
            resolved_at DATETIME DEFAULT NULL,
            response_time_seconds INTEGER DEFAULT NULL
        )''')

        # Rooms table for evacuation routing
        db.execute('''CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT NOT NULL UNIQUE,
            floor_number INTEGER DEFAULT 1,
            room_type TEXT DEFAULT 'guest',
            x_position REAL DEFAULT 0,
            y_position REAL DEFAULT 0,
            capacity INTEGER DEFAULT 2,
            occupied INTEGER DEFAULT 0,
            guest_name TEXT DEFAULT NULL,
            emergency_exit TEXT DEFAULT NULL
        )''')

        # Emergency exits table
        db.execute('''CREATE TABLE IF NOT EXISTS exits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exit_name TEXT NOT NULL,
            floor_number INTEGER DEFAULT 1,
            x_position REAL DEFAULT 0,
            y_position REAL DEFAULT 0,
            exit_type TEXT DEFAULT 'stairwell',
            status TEXT DEFAULT 'open'
        )''')

        # Resources table
        db.execute('''CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_name TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            floor_number INTEGER DEFAULT 1,
            room_number TEXT DEFAULT NULL,
            quantity INTEGER DEFAULT 1,
            status TEXT DEFAULT 'available',
            last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # Emergency contacts table
        db.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_type TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT NULL,
            address TEXT DEFAULT NULL,
            priority INTEGER DEFAULT 1
        )''')

        # Staff/escalation levels table
        db.execute('''CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'security',
            phone TEXT DEFAULT NULL,
            email TEXT DEFAULT NULL,
            escalation_level INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1
        )''')

        # Offline queue for PWA
        db.execute('''CREATE TABLE IF NOT EXISTS offline_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            synced INTEGER DEFAULT 0
        )''')

        # Analytics table
        db.execute('''CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emergency_id INTEGER,
            event_type TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            data TEXT DEFAULT NULL
        )''')

        # Guest approvals table
        db.execute('''CREATE TABLE IF NOT EXISTS guest_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT DEFAULT NULL,
            phone TEXT DEFAULT NULL,
            room_number TEXT DEFAULT NULL,
            request_reason TEXT DEFAULT NULL,
            status TEXT DEFAULT 'pending',
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            approved_by TEXT DEFAULT NULL,
            approved_at DATETIME DEFAULT NULL
        )''')

        # Insert default staff
        db.execute('''INSERT OR IGNORE INTO staff (username, password, name, role, escalation_level)
                        VALUES ('admin', 'rescue123', 'Admin User', 'admin', 1)''')
        db.execute('''INSERT OR IGNORE INTO staff (username, password, name, role, escalation_level)
                        VALUES ('manager', 'manager123', 'Manager User', 'manager', 2)''')
        db.execute('''INSERT OR IGNORE INTO staff (username, password, name, role, escalation_level)
                        VALUES ('director', 'director123', 'Director User', 'director', 3)''')

        # Insert sample rooms
        for i in range(1, 11):
            db.execute('''INSERT OR IGNORE INTO rooms (room_number, floor_number, room_type, x_position, y_position, capacity, occupied)
                          VALUES (?, 1, 'guest', ?, ?, 2, 1)''',
                          (f'10{i}', i * 10.0, 50.0))

        # Insert sample exits
        db.execute('''INSERT OR IGNORE INTO exits (exit_name, floor_number, x_position, y_position, exit_type)
                        VALUES ('Main Exit', 1, 5.0, 5.0, 'main_door')''')
        db.execute('''INSERT OR IGNORE INTO exits (exit_name, floor_number, x_position, y_position, exit_type)
                        VALUES ('Emergency Stairwell A', 1, 95.0, 5.0, 'stairwell')''')
        db.execute('''INSERT OR IGNORE INTO exits (exit_name, floor_number, x_position, y_position, exit_type)
                        VALUES ('Emergency Exit B', 1, 5.0, 95.0, 'fire_exit')''')

        # Insert sample resources
        db.execute('''INSERT OR IGNORE INTO resources (resource_name, resource_type, floor_number, quantity, status)
                        VALUES ('First-Aid Kit A', 'first_aid', 1, 1, 'available')''')
        db.execute('''INSERT OR IGNORE INTO resources (resource_name, resource_type, floor_number, quantity, status)
                        VALUES ('Fire Extinguisher A', 'fire_extinguisher', 1, 1, 'available')''')
        db.execute('''INSERT OR IGNORE INTO resources (resource_name, resource_type, floor_number, quantity, status)
                        VALUES ('Oxygen Cylinder A', 'oxygen', 1, 1, 'available')''')
        db.execute('''INSERT OR IGNORE INTO resources (resource_name, resource_type, floor_number, quantity, status)
                        VALUES ('AED Device', 'aed', 1, 1, 'available')''')

        # Insert emergency contacts
        db.execute('''INSERT OR IGNORE INTO contacts (name, contact_type, phone, priority)
                        VALUES ('City Hospital', 'hospital', '911-0001', 1)''')
        db.execute('''INSERT OR IGNORE INTO contacts (name, contact_type, phone, priority)
                        VALUES ('Fire Station 1', 'fire', '911-0002', 1)''')
        db.execute('''INSERT OR IGNORE INTO contacts (name, contact_type, phone, priority)
                        VALUES ('Police Station', 'police', '911-0003', 1)''')
        db.execute('''INSERT OR IGNORE INTO contacts (name, contact_type, phone, priority)
                        VALUES ('Ambulance Service', 'ambulance', '911-0004', 1)''')

        # Insert demo approved guest
        db.execute('''INSERT OR IGNORE INTO guest_approvals (username, password, name, email, phone, room_number, request_reason, status, approved_by, approved_at)
                        VALUES ('guest1', 'guest123', 'John Guest', 'guest@hotel.com', '555-0101', '101', 'Demo access', 'approved', 'admin', ?)''',
                        (datetime.now(),))

        db.commit()

def close_db(e=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

