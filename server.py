#SoyuzMessenger
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_socketio import SocketIO, send, emit, disconnect
from datetime import datetime
from time import time
from werkzeug.utils import secure_filename
import json, os
from collections import defaultdict, deque
import ast

# تنظیمات اولیه
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")
UPLOAD_FOLDER = 'uploads'
USERS_FILE = 'users.json'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def current_time():
    return datetime.utcnow().isoformat() + 'Z' #iso 8601 standard time

# متغیرهای وضعیت
cooldown_warnings = {}  # کلید: (username, ip)، مقدار: timestamp آخرین اخطار ۲ ثانیه‌ای
last_message_time = {}  # کلید: (username, ip) / مقدار: timestamp آخرین پیام
users = {}
active_users = set()
user_sockets = {}
user_ip_message_timestamps = defaultdict(lambda: deque(maxlen=5))  # کلید: (username, ip)، مقدار: deque از زمان‌ها
banned_users = {}  # کلید: (username, ip)، مقدار: زمان انقضای بن
user_ip_ban_notification_count = defaultdict(int) # کلید: (username, ip)، مقدار: تعداد دفعات ارسال پیام بن شدن
IP_BAN_THRESHOLD = 5
IP_BAN_DURATION = 1200  # ۲۰ دقیقه بن
IP_WARN_THRESHOLD = 3 # ارسال هشدار بعد از این تعداد پیام در بازه زمانی
# بن دائمی و لاگ اسپم
PERMA_BANNED_FILE = 'perma_banned.json'

if not os.path.exists(PERMA_BANNED_FILE):
    with open(PERMA_BANNED_FILE, 'w') as f:
        json.dump([], f)

with open(PERMA_BANNED_FILE, 'r') as f:
    try:
        PERMA_BANNED_USERS = set(json.load(f))
    except json.JSONDecodeError:
        PERMA_BANNED_USERS = set()

SPAM_LOG_FILE = 'spam_log.txt'
TEMP_BAN_FILE = 'temp_bans.json'

# بارگذاری بن‌های موقت از فایل
if os.path.exists(TEMP_BAN_FILE):
    with open(TEMP_BAN_FILE, 'r') as f:
        try:
            banned_users = {ast.literal_eval(k): v for k, v in json.load(f).items()}
        except:
            banned_users = {}

# بررسی بن دائمی
def is_banned_permanently(username):
    return username in PERMA_BANNED_USERS

# لاگ کردن تلاش‌های اسپم
def log_spam_attempt(username, ip, reason):
    log_entry = f"[{current_time()}] USER: {username} | IP: {ip} | REASON: {reason}\n"
    with open(SPAM_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)

# بارگذاری کاربران از فایل
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        users = {u['username']: u for u in json.load(f)}

# صفحات اصلی
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

# ثبت‌نام و ورود
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

# پروفایل
@app.route('/get_profile')
def get_profile():
    username = request.args.get('username')
    if not username or username not in users:
        return jsonify({'success': False, 'error': 'کاربر یافت نشد'}), 404
    user = users[username]
    return jsonify({'success': True, 'name': user['name'], 'profile_picture': user.get('profile_picture')})

@app.route('/auth/update_profile', methods=['POST'])
def update_profile():
    username = request.form.get('username')
    if not username or username not in users:
        return jsonify({'success': False, 'error': 'کاربر معتبر نیست'}), 400

    new_name = request.form.get('displayName')
    file = request.files.get('profilePicture')

    if new_name:
        users[username]['name'] = new_name
        session['name'] = new_name

    if file:
        ext = os.path.splitext(file.filename)[1]
        filename = secure_filename(f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        users[username]['profile_picture'] = f"uploads/{filename}"

    save_users()
    return jsonify({'success': True, 'profile_picture': users[username].get('profile_picture')})

# آپلود فایل‌ها
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

# WebSocket ها
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('join')
def handle_join(data):
    username = data.get('username')
    if username:
        active_users.add(username)
        user_sockets[request.sid] = username
        emit('online_users', {'count': len(active_users)}, broadcast=True)
        send(system_message(f"{users[username]['name']} وارد شد"), broadcast=True)

@socketio.on('left')
def handle_left(data):
    username = data.get('username')
    if username:
        active_users.discard(username)
        user_sockets.pop(request.sid, None)
        emit('online_users', {'count': len(active_users)}, broadcast=True)
        send(system_message(f"{users[username]['name']} خارج شد"), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = user_sockets.pop(request.sid, None)
    if username:
        active_users.discard(username)
        emit('online_users', {'count': len(active_users)}, broadcast=True)
        send(system_message(f"{users[username]['name']} قطع اتصال شد"), broadcast=True)

@socketio.on('message')
def handle_message(data):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    username = session.get('username', 'ناشناس')
    user_ip_key = (username, ip)
    now = time()

    # بررسی بن دائمی
    if is_banned_permanently(username):
        emit('message', {
            'sender_username': 'System',
            'sender_name': 'System',
            'msg': f'⛔️ کاربر "{username}" برای همیشه بن شده است.',
            'time': current_time(),
            'is_system': True
        }, to=request.sid)
        return

    # محدودیت "هر ۲ ثانیه فقط یک پیام"
    last_time = last_message_time.get(user_ip_key, 0)
    if now - last_time < 2:
        if now - cooldown_warnings.get(user_ip_key, 0) > 10:
            emit('message', {
                'sender_username': 'System',
                'sender_name': 'System',
                'msg': f'⏱️ لطفاً صبر کنید! فقط هر ۲ ثانیه یک پیام مجاز است.',
                'time': current_time(),
                'is_system': True
            }, to=request.sid)
            cooldown_warnings[user_ip_key] = now
        return



    # ثبت زمان آخرین پیام
    last_message_time[user_ip_key] = now


    # بررسی بن موقت
    if user_ip_key in banned_users and now < banned_users[user_ip_key]:
        if user_ip_ban_notification_count[user_ip_key] < 2:
            emit('message', {
                'sender_username': 'System',
                'sender_name': 'System',
                'msg': f'🚫 کاربر "{username}" به دلیل ارسال بیش از حد پیام موقتاً بن شده است. لطفاً بعداً امتحان کنید.',
                'time': current_time(),
                'is_system': True
            }, to=request.sid)
            user_ip_ban_notification_count[user_ip_key] += 1
        return

    # سیستم ضد اسپم جدید
    timestamps = user_ip_message_timestamps[user_ip_key]
    timestamps.append(now)
    timestamps = deque([t for t in timestamps if now - t < 5], maxlen=10)
    user_ip_message_timestamps[user_ip_key] = timestamps

    if len(timestamps) > 3:
        banned_users[user_ip_key] = now + IP_BAN_DURATION
        save_temp_bans()
        emit('message', {
            'sender_username': 'System',
            'sender_name': 'System',
            'msg': f'🚨 اسپم شناسایی شد! "{username}" به مدت {IP_BAN_DURATION // 60} دقیقه بن شد.',
            'time': current_time(),
            'is_system': True
        }, to=request.sid)
        log_spam_attempt(username, ip, 'Temporary ban applied (spam rate exceeded)')
        return


    # پیام نرمال
    name = session.get('name', 'کاربر')
    profile_picture = users.get(username, {}).get("profile_picture", "")

    data.update({
        'sender_username': username,
        'sender_name': name,
        'profile_picture': profile_picture,
        'time': current_time()
    })

    send(data, broadcast=True) 

# توابع کمکی
def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(list(users.values()), f, indent=2)

def system_message(msg):
    return {
        'sender_username': 'System',
        'sender_name': 'System',
        'msg': msg,
        'time': current_time(),
        'is_system': True
    }

def current_time():
    return datetime.utcnow().isoformat() + 'Z' #iso 8601 standard time

def save_temp_bans():
    with open(TEMP_BAN_FILE, 'w') as f:
        json.dump({str(k): v for k, v in banned_users.items()}, f)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)


