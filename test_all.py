import urllib.request
import http.cookiejar
import json

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# Login
req = urllib.request.Request('http://127.0.0.1:5000/login', data=b'username=admin&password=rescue123', headers={'Content-Type':'application/x-www-form-urlencoded'})
resp = opener.open(req)
print('Login:', resp.geturl())

# Trigger panic
data = json.dumps({'name':'Test Guest','location':'Room 105','room_number':'105','emergency_type':'fire'}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/panic', data=data, headers={'Content-Type':'application/json'})
resp = json.loads(opener.open(req).read())
emergency_id = resp['id']
print('Panic ID:', emergency_id)

# Test all pages
pages = [
    ('/', 'Home'),
    ('/dashboard', 'Dashboard'),
    ('/track/' + str(emergency_id), 'Track'),
    ('/status/' + str(emergency_id), 'Status'),
    ('/evacuation/105', 'Evacuation'),
    ('/incident-log', 'Incident Log'),
    ('/resources', 'Resources'),
    ('/contacts', 'Contacts'),
    ('/staff/profile', 'Staff Profile'),
    ('/api/analytics', 'Analytics API'),
]

for url, name in pages:
    try:
        resp = opener.open('http://127.0.0.1:5000' + url)
        print(f'{name}: OK ({resp.getcode()}, {len(resp.read())} bytes)')
    except Exception as e:
        print(f'{name}: FAILED - {e}')

# Update status
data = json.dumps({'status':'in-progress','note':'Team dispatched'}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/update_status/' + str(emergency_id), data=data, headers={'Content-Type':'application/json'})
resp = opener.open(req)
print('Update Status:', resp.getcode(), json.loads(resp.read())['message'])

# AI Detect
req = urllib.request.Request('http://127.0.0.1:5000/api/ai-detect', data=b'{"sensor_data":"camera_a"}', headers={'Content-Type':'application/json'})
resp = json.loads(opener.open(req).read())
print('AI Detect:', resp)

print('\n=== ALL TESTS COMPLETE ===')
