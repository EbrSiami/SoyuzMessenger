#auth.py
from flask import Blueprint, render_template, request, jsonify, session, redirect
import json
import os

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

USERS_FILE = 'users.json'
# ساختار موقت برای نگهداری کاربران
users = {} # تغییر ساختار برای ذخیره اسم هم
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        try:
            data = json.load(f)
            users = {user['username']: {'password': user['password'], 'name': user['name']} for user in data}
        except json.JSONDecodeError:
            users = {}

@auth_bp.route('/simple_signup', methods=['POST'])
def simple_signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    name = data.get('name') # دریافت اسم

    if not username or not password or not name:
        return jsonify({'error': 'Username, password, and display name are required.'}), 400

    if username in users:
        return jsonify({'error': 'Username already exists.'}), 409

    users[username] = {'password': password, 'name': name} # ذخیره اسم
    # ذخیره اطلاعات در فایل
    user_list = [{'username': u, 'password': users[u]['password'], 'name': users[u]['name']} for u in users]
    with open(USERS_FILE, 'w') as f:
        json.dump(user_list, f)
    return jsonify({'message': 'Signup successful.'}), 201

@auth_bp.route('/simple_login', methods=['POST'])
def simple_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    if username in users and users[username]['password'] == password:
        session['username'] = username
        session['name'] = users[username]['name'] # ذخیره اسم در session
        return jsonify({'message': 'Login successful.'}), 200
    else:
        return jsonify({'error': 'Invalid username or password.'}), 401

@auth_bp.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('name', None)
    return redirect('/') # هدایت به صفحه اصلی
