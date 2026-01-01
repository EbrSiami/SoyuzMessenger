# -- server.py --

#SoyuzMessenger


# * STOP THE GENOCIDE.
# * FREE PALESTINE. 🇵🇸
# * Coding for a world where every human life is valued equally.

# Author: Ebrahim Siami
# Date : 09/08/2024

from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_socketio import SocketIO, send, emit
from datetime import datetime
from time import time
from werkzeug.utils import secure_filename
from collections import defaultdict, deque
import json
import os
import ast

# --- Configuration & Setup ---
app = Flask(__name__)
# In production, use environment variable for secret key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key_change_in_prod')
# Enable CORS for development flexibility
socketio = SocketIO(app, cors_allowed_origins="*")

# File Paths
UPLOAD_FOLDER = 'uploads'
USERS_FILE = 'users.json'
PERMA_BANNED_FILE = 'perma_banned.json'
SPAM_LOG_FILE = 'spam_log.txt'
TEMP_BAN_FILE = 'temp_bans.json'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- In-Memory Data Structures ---
# NOTE: For a scalable production app, these should be replaced by a database (SQL/Redis).
users = {}
active_users = set()
user_sockets = {}  # Map: sid -> username

# Security & Anti-Spam State
cooldown_warnings = {}      # Key: (username, ip) -> last warning timestamp
last_message_time = {}      # Key: (username, ip) -> last message timestamp
user_ip_message_timestamps = defaultdict(lambda: deque(maxlen=5))  # Sliding window for rate limiting
banned_users = {}           # Key: (username, ip) -> unban timestamp
user_ip_ban_notification_count = defaultdict(int) 
PERMA_BANNED_USERS = set()

# Constants
IP_BAN_THRESHOLD = 5        # Max messages in short window
IP_BAN_DURATION = 1200      # 20 Minutes (in seconds)
IP_WARN_THRESHOLD = 3

# --- Helper Functions ---

def current_time():
    """Returns ISO 8601 formatted UTC time string."""
    return datetime.utcnow().isoformat() + 'Z'

def save_users():
    """Persists user data to JSON file."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(users.values()), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving users: {e}")

def save_temp_bans():
    """Persists temporary bans to prevent bypass on restart."""
    with open(TEMP_BAN_FILE, 'w', encoding='utf-8') as f:
        # Convert tuple keys to string for JSON compatibility
        json.dump({str(k): v for k, v in banned_users.items()}, f)

def log_spam_attempt(username, ip, reason):
    """Logs suspicious activities for auditing."""
    log_entry = f"[{current_time()}] USER: {username} | IP: {ip} | REASON: {reason}\n"
    with open(SPAM_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)

def system_message(msg):
    """Constructs a standardized system notification packet."""
    return {
        'sender_username': 'System',
        'sender_name': 'System',
        'msg': msg,
        'time': current_time(),
        'is_system': True
    }

# --- Initialization ---

# Load Users
if os.path.exists(USERS_FILE):
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            users = {u['username']: u for u in data}
    except (json.JSONDecodeError, KeyError):
        users = {}

# Load Permabans
if not os.path.exists(PERMA_BANNED_FILE):
    with open(PERMA_BANNED_FILE, 'w') as f:
        json.dump([], f)
else:
    with open(PERMA_BANNED_FILE, 'r', encoding='utf-8') as f:
        try:
            PERMA_BANNED_USERS = set(json.load(f))
        except json.JSONDecodeError:
            PERMA_BANNED_USERS = set()

# Load Temp Bans
if os.path.exists(TEMP_BAN_FILE):
    with open(TEMP_BAN_FILE, 'r', encoding='utf-8') as f:
        try:
            # Convert string keys back to tuples
            banned_users = {ast.literal_eval(k): v for k, v in json.load(f).items()}
        except:
            banned_users = {}

# --- HTTP Routes ---

@app.route('/')
def index():
    if 'username' in session:
        return render_template('chat.html', username=session['username'], name=session.get('name'))
    return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/auth/simple_signup', methods=['POST'])
def simple_signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    name = data.get('name')

    if not username or not password or not name:
        return jsonify({'error': 'تمام فیلدها الزامی هستند.'}), 400
    if username in users:
        return jsonify({'error': 'این نام کاربری قبلاً ثبت شده.'}), 409

    # Note: Password hashing should be implemented here for production.
    users[username] = {'username': username, 'password': password, 'name': name}
    save_users()
    return jsonify({'message': 'ثبت‌نام موفق بود'}), 201

@app.route('/auth/simple_login', methods=['POST'])
def simple_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if username in users and users[username]['password'] == password:
        session['username'] = username
        session['name'] = users[username]['name']
        return jsonify({'message': 'ورود موفق بود'}), 200
    return jsonify({'error': 'نام کاربری یا رمز عبور اشتباه است'}), 401

@app.route('/get_profile')
def get_profile():
    username = request.args.get('username')
    if not username or username not in users:
        return jsonify({'success': False, 'error': 'کاربر یافت نشد'}), 404
    user = users[username]
    return jsonify({
        'success': True, 
        'name': user['name'], 
        'profile_picture': user.get('profile_picture')
    })

@app.route('/auth/update_profile', methods=['POST'])
def update_profile():
    username = request.form.get('username')
    # Basic authorization check
    if not username or username not in users:
        return jsonify({'success': False, 'error': 'کاربر معتبر نیست'}), 400
    
    # Check if the user making the request is actually the logged-in user
    if session.get('username') != username:
         return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    new_name = request.form.get('displayName')
    file = request.files.get('profilePicture')

    if new_name:
        users[username]['name'] = new_name
        session['name'] = new_name

    if file:
        ext = os.path.splitext(file.filename)[1]
        # Generate unique filename to prevent overwrites
        filename = secure_filename(f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        users[username]['profile_picture'] = f"uploads/{filename}"

    save_users()
    return jsonify({'success': True, 'profile_picture': users[username].get('profile_picture')})

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

# --- WebSocket Events (Socket.IO) ---

@socketio.on('connect')
def handle_connect():
    print(f"New connection: {request.sid}")

@socketio.on('join')
def handle_join(data):
    username = data.get('username')
    if username:
        active_users.add(username)
        user_sockets[request.sid] = username
        emit('online_users', {'count': len(active_users)}, broadcast=True)
        send(system_message(f"{users[username]['name']} وارد شد"), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = user_sockets.pop(request.sid, None)
    if username:
        active_users.discard(username)
        emit('online_users', {'count': len(active_users)}, broadcast=True)
        send(system_message(f"{users[username]['name']} قطع اتصال شد"), broadcast=True)

@socketio.on('message')
def handle_message(data):
    """
    Main message handler with sophisticated spam protection logic.
    """
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    username = session.get('username', 'ناشناس')
    user_ip_key = (username, ip)
    now = time()

    # 1. Check Permanent Ban
    if username in PERMA_BANNED_USERS:
        emit('message', system_message(f'⛔️ کاربر "{username}" برای همیشه بن شده است.'), to=request.sid)
        return

    # 2. Rate Limiting (Hard Cooldown: 2 seconds)
    last_time = last_message_time.get(user_ip_key, 0)
    if now - last_time < 2:
        # Send warning only once every 10 seconds to avoid flooding the user
        if now - cooldown_warnings.get(user_ip_key, 0) > 10:
            emit('message', system_message('⏱️ لطفاً صبر کنید! ارسال پیام خیلی سریع است.'), to=request.sid)
            cooldown_warnings[user_ip_key] = now
        return

    last_message_time[user_ip_key] = now

    # 3. Check Temporary Ban Status
    if user_ip_key in banned_users:
        if now < banned_users[user_ip_key]:
            # Notify user sparingly
            if user_ip_ban_notification_count[user_ip_key] < 2:
                emit('message', system_message(f'🚫 شما به دلیل ارسال اسپم موقتاً بن هستید.'), to=request.sid)
                user_ip_ban_notification_count[user_ip_key] += 1
            return
        else:
            # Ban expired
            del banned_users[user_ip_key]
            user_ip_ban_notification_count[user_ip_key] = 0

    # 4. Heuristic Spam Detection (Sliding Window)
    timestamps = user_ip_message_timestamps[user_ip_key]
    timestamps.append(now)
    # Keep only timestamps within the last 5 seconds
    # This logic creates a sliding window of recent messages
    new_timestamps = deque([t for t in timestamps if now - t < 5], maxlen=10)
    user_ip_message_timestamps[user_ip_key] = new_timestamps

    # If more than 3 messages in 5 seconds -> Ban
    if len(new_timestamps) > 3:
        banned_users[user_ip_key] = now + IP_BAN_DURATION
        save_temp_bans()
        emit('message', system_message(f'🚨 اسپم شناسایی شد! به مدت {IP_BAN_DURATION // 60} دقیقه بن شدید.'), to=request.sid)
        log_spam_attempt(username, ip, 'Temporary ban: Rate limit exceeded')
        return

    # 5. Broadcast Valid Message
    sender_name = session.get('name', 'کاربر')
    profile_picture = users.get(username, {}).get("profile_picture", "")

    # Construct clean message payload
    message_payload = {
        'sender_username': username,
        'sender_name': sender_name,
        'profile_picture': profile_picture,
        'msg': data.get('msg', ''), # Ensure msg exists
        'time': current_time(),
        'is_system': False
    }

    send(message_payload, broadcast=True)

if __name__ == '__main__':
    # Run the server
    print("🚀 SoyuzMessenger Server Starting...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)