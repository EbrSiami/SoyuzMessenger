# -- auth.py --

#SoyuzMessenger


# * STOP THE GENOCIDE.
# * FREE PALESTINE. 🇵🇸
# * Coding for a world where every human life is valued equally.

# Author: Ebrahim Siami

# Date : 09/07/2024

"""
Authentication Module
---------------------
Handles user registration, login, and session management.
Data is stored in a JSON file for demonstration purposes.
"""

from flask import Blueprint, request, jsonify, session, redirect
import json
import os

# Create a Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

USERS_FILE = 'users.json'

# Load existing users into memory on server start
# Structure: {username: {'password': '...', 'name': '...'}}
users = {}

if os.path.exists(USERS_FILE):
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Convert list of dicts to a dictionary for faster lookup (O(1))
            users = {
                user['username']: {
                    'password': user['password'],
                    'name': user.get('name', user['username'])
                } for user in data
            }
    except json.JSONDecodeError:
        print("Warning: users.json is empty or corrupted. Starting with empty database.")
        users = {}

@auth_bp.route('/simple_signup', methods=['POST'])
def simple_signup():
    """
    Handle user registration.
    
    Expects JSON: { "username": "...", "password": "...", "name": "..." }
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    name = data.get('name')

    # 1. Validation
    if not username or not password or not name:
        return jsonify({'error': 'All fields (username, password, display name) are required.'}), 400

    # 2. Check for duplicates
    if username in users:
        return jsonify({'error': 'Username already exists.'}), 409

    # 3. Save User
    # NOTE: In a production environment, passwords must be hashed (e.g., using bcrypt or Argon2).
    # Storing plain-text passwords is done here strictly for educational simplicity.
    users[username] = {'password': password, 'name': name}

    # Persist to JSON file
    try:
        user_list = [
            {'username': u, 'password': users[u]['password'], 'name': users[u]['name']} 
            for u in users
        ]
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_list, f, ensure_ascii=False, indent=4)
            
        return jsonify({'message': 'Signup successful.'}), 201
    except Exception as e:
        return jsonify({'error': 'Internal Server Error during data saving.'}), 500

@auth_bp.route('/simple_login', methods=['POST'])
def simple_login():
    """
    Handle user login.
    Checks credentials and sets up the server-side session.
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    # Verify credentials
    if username in users and users[username]['password'] == password:
        # Create Session
        session['username'] = username
        session['name'] = users[username]['name']
        return jsonify({'message': 'Login successful.'}), 200
    else:
        return jsonify({'error': 'Invalid username or password.'}), 401

@auth_bp.route('/logout')
def logout():
    """
    Clear user session and redirect to login page.
    """
    session.pop('username', None)
    session.pop('name', None)
    return redirect('/')