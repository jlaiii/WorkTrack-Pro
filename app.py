# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app) # Enable CORS for frontend to communicate with backend

# Define paths for JSON data files
USERS_FILE = 'users.json'
TIME_ENTRIES_FILE = 'time_entries.json'
NOTES_FILE = 'notes.json' # New file for all notes

# --- Helper Functions for JSON File Operations ---

def load_data(file_path):
    """Loads data from a JSON file."""
    if not os.path.exists(file_path):
        # Create an empty file if it doesn't exist
        with open(file_path, 'w') as f:
            json.dump([], f)
        return []
    with open(file_path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # Handle empty or malformed JSON files
            print(f"Warning: {file_path} is empty or malformed. Initializing as empty list.")
            return []

def save_data(file_path, data):
    """Saves data to a JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# --- Default User Configuration ---
DEFAULT_USERS_CONFIG = [
    {'name': 'System Admin', 'email': 'admin@example.com', 'role': 'ADMIN', 'pin': '0000', 'phone': '555-111-2222'},
    {'name': 'Lead Timekeeper', 'email': 'timekeeper@example.com', 'role': 'TIMEKEEPER', 'pin': '1111', 'phone': '555-333-4444'},
    {'name': 'John Doe', 'email': 'john@example.com', 'role': 'worker', 'pin': '1234', 'phone': '555-555-6666'}
]

# --- Initialize/Correct User Data on Startup ---
def initialize_users():
    global users
    users = load_data(USERS_FILE)
    updated_users = False

    for default_user_data in DEFAULT_USERS_CONFIG:
        # Check if a user with this PIN already exists
        existing_user = next((u for u in users if u.get('pin') == default_user_data['pin']), None)

        if existing_user:
            # If exists, ensure role is correct
            if existing_user.get('role') != default_user_data['role']:
                print(f"Log: Correcting role for user '{existing_user.get('name', 'N/A')}' (PIN: {default_user_data['pin']}): from '{existing_user.get('role')}' to '{default_user_data['role']}'")
                existing_user['role'] = default_user_data['role']
                updated_users = True
            # Also ensure other fields like name/email/phone are consistent if they are meant to be fixed
            if existing_user.get('name') != default_user_data['name']:
                existing_user['name'] = default_user_data['name']
                updated_users = True
            if existing_user.get('email') != default_user_data['email']:
                existing_user['email'] = default_user_data['email']
                updated_users = True
            if existing_user.get('phone') != default_user_data['phone']:
                existing_user['phone'] = default_user_data['phone']
                updated_users = True
            # Ensure is_suspended field exists and defaults to False if not present
            if 'is_suspended' not in existing_user:
                existing_user['is_suspended'] = False
                updated_users = True
            # Ensure suspension_notes field exists and defaults to [] if not present
            if 'suspension_notes' not in existing_user:
                existing_user['suspension_notes'] = []
                updated_users = True
        else:
            # If not exists, add the default user
            new_user = {
                'id': str(uuid.uuid4()),
                'name': default_user_data['name'],
                'email': default_user_data['email'],
                'phone': default_user_data['phone'],
                'role': default_user_data['role'],
                'pin': default_user_data['pin'],
                'createdAt': datetime.now().isoformat(),
                'is_suspended': False, # New field for suspension status
                'suspension_notes': [] # New field to store suspension notes
            }
            users.append(new_user)
            updated_users = True
            print(f"Log: Adding default user: {new_user['name']} with role '{new_user['role']}' and PIN '{new_user['pin']}'")

    if updated_users:
        save_data(USERS_FILE, users)
        print("Log: users.json updated with default user configurations.")
    else:
        print("Log: users.json is already configured correctly with default users.")

# Load initial data and ensure defaults are set/corrected
initialize_users()
time_entries = load_data(TIME_ENTRIES_FILE)
notes = load_data(NOTES_FILE) # Load notes data


# --- API Endpoints ---

@app.route('/login_pin', methods=['POST'])
def login_pin():
    """Handles login for all roles using a PIN."""
    data = request.get_json()
    pin = data.get('pin')

    print(f"Log: Attempting login for PIN: {pin}")

    # Validate PIN: must be a string containing only digits and not empty
    if not pin or not isinstance(pin, str) or not pin.isdigit():
        print(f"Log: Login failed for PIN '{pin}': Invalid PIN format.")
        return jsonify({'message': 'PIN must be a non-empty number.'}), 400

    user = next((u for u in users if u['pin'] == pin), None)

    if user:
        if user.get('is_suspended', False):
            print(f"Log: Login failed for user '{user.get('name', 'N/A')}' (PIN: {pin}): Account is suspended.")
            return jsonify({'message': 'Account is suspended. Please contact your administrator.'}), 403

        print(f"Log: Login successful for user '{user['name']}' (ID: {user['id']}, Role: {user['role']}).")
        # Return a simplified user object for the frontend
        return jsonify({'message': 'Login successful', 'user': {'id': user['id'], 'name': user['name'], 'email': user.get('email'), 'role': user['role'], 'pin': user['pin']}}), 200
    else:
        print(f"Log: Login failed for PIN '{pin}': Invalid PIN.")
        return jsonify({'message': 'Invalid PIN.'}), 401

@app.route('/get_worker_status_by_pin', methods=['POST'])
def get_worker_status_by_pin():
    """Retrieves worker status and last session details based on PIN, plus all historical entries."""
    data = request.get_json()
    pin = data.get('pin')

    # This endpoint specifically checks for 'worker' role
    user = next((u for u in users if u['pin'] == pin and u['role'] == 'worker'), None)

    if not user:
        print(f"Log: Failed to get worker status for PIN '{pin}': Invalid PIN or not a worker account.")
        return jsonify({'message': 'Invalid PIN or not a worker account.'}), 401

    if user.get('is_suspended', False):
        print(f"Log: Failed to get worker status for user '{user.get('name', 'N/A')}' (PIN: {pin}): Account is suspended.")
        return jsonify({'message': 'Account is suspended. Please contact your administrator.'}), 403

    user_id = user['id']
    is_clocked_in = False
    current_session_start = None
    last_session_total_hours = None
    last_session_login_time = None
    last_session_logout_time = None

    # Get all entries for the user, sorted by login time descending
    user_time_entries = sorted(
        [entry for entry in time_entries if entry['userId'] == user_id],
        key=lambda x: datetime.fromisoformat(x['loginTime']),
        reverse=True
    )

    # Check if user is currently clocked in
    active_entry = next((entry for entry in user_time_entries if entry['logoutTime'] is None), None)
    if active_entry:
        is_clocked_in = True
        current_session_start = datetime.fromisoformat(active_entry['loginTime']).isoformat()
    else:
        # Get the last completed session if not clocked in
        completed_entries = [entry for entry in user_time_entries if entry['logoutTime'] is not None]
        if completed_entries:
            last_session = completed_entries[0] # Already sorted, so first is most recent
            last_session_total_hours = last_session['totalHours']
            last_session_login_time = datetime.fromisoformat(last_session['loginTime']).isoformat()
            last_session_logout_time = datetime.fromisoformat(last_session['logoutTime']).isoformat()

    # Hydrate notes for historical entries
    historical_entries_with_notes = []
    for entry in user_time_entries:
        entry_copy = entry.copy()
        # Retrieve full note objects using their IDs
        entry_copy['editNotesFull'] = [n for n in notes if n['id'] in entry.get('editNotes', [])]
        historical_entries_with_notes.append(entry_copy)


    print(f"Log: Worker status retrieved for user '{user['name']}' (ID: {user_id}). Clocked in: {is_clocked_in}.")
    return jsonify({
        'user': {'id': user['id'], 'name': user['name'], 'email': user.get('email'), 'role': user['role']},
        'is_clocked_in': is_clocked_in,
        'current_session_start': current_session_start,
        'last_session_total_hours': last_session_total_hours,
        'last_session_login_time': last_session_login_time,
        'last_session_logout_time': last_session_logout_time,
        'historical_entries': historical_entries_with_notes # Return hydrated notes
    }), 200

@app.route('/clock_in', methods=['POST'])
def clock_in():
    """Records a user's clock-in time."""
    data = request.get_json()
    user_id = data.get('user_id')

    # Ensure the user exists (any role can clock in/out themselves if they have a user_id)
    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        print(f"Log: Clock-in failed for user_id '{user_id}': User not found.")
        return jsonify({'message': 'User not found.'}), 404

    if user.get('is_suspended', False):
        print(f"Log: Clock-in failed for user '{user.get('name', 'N/A')}' (ID: {user_id}): User is suspended.")
        return jsonify({'message': 'User is suspended and cannot clock in.'}), 403

    # Check if user is already clocked in
    active_entry = next((entry for entry in time_entries if entry['userId'] == user_id and entry['logoutTime'] is None), None)
    if active_entry:
        print(f"Log: Clock-in failed for user '{user['name']}' (ID: {user_id}): Already clocked in.")
        return jsonify({'message': 'Already clocked in'}), 400

    new_entry = {
        'id': str(uuid.uuid4()),
        'userId': user_id,
        'loginTime': datetime.now().isoformat(),
        'logoutTime': None,
        'totalHours': 0,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'edited': False, # New field to indicate if entry was edited
        'lastModified': datetime.now().isoformat(), # Add last modified timestamp
        'editNotes': [] # Store note IDs
    }
    time_entries.append(new_entry)
    save_data(TIME_ENTRIES_FILE, time_entries)
    print(f"Log: User '{user['name']}' (ID: {user_id}) clocked in at {new_entry['loginTime']}.")
    return jsonify({'message': f'Thank you, {user["name"]}! You have been clocked in.'}), 200

@app.route('/clock_out', methods=['POST'])
def clock_out():
    """Records a user's clock-out time and calculates total hours.
    Consolidates multiple clock-in/out events on the same day into one entry."""
    data = request.get_json()
    user_id = data.get('user_id')

    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        print(f"Log: Clock-out failed for user_id '{user_id}': User not found.")
        return jsonify({'message': 'User not found.'}), 404

    # Find the active clock-in entry
    active_entry = next((entry for entry in time_entries if entry['userId'] == user_id and entry['logoutTime'] is None), None)

    if active_entry:
        login_time = datetime.fromisoformat(active_entry['loginTime'])
        logout_time = datetime.now()
        current_session_duration = logout_time - login_time
        current_session_hours = round(current_session_duration.total_seconds() / 3600, 2)

        # Find if there's an existing completed entry for today
        today_date_str = datetime.now().strftime('%Y-%m-%d')
        existing_today_entry = next(
            (entry for entry in time_entries
             if entry['userId'] == user_id
             and entry['date'] == today_date_str
             and entry['logoutTime'] is not None # Ensure it's a completed entry
             and datetime.fromisoformat(entry['loginTime']).date() == logout_time.date()), # Check if it's for today
            None
        )

        old_logout_time = active_entry['logoutTime']
        old_total_hours = active_entry['totalHours']

        if existing_today_entry:
            # If an entry for today already exists, add current session hours to it
            # and remove the active entry (as it's now consolidated)
            print(f"Log: Consolidating clock-out for user '{user['name']}' (ID: {user_id}) into existing entry for {today_date_str}.")
            existing_today_entry['totalHours'] = round(existing_today_entry['totalHours'] + current_session_hours, 2)
            existing_today_entry['logoutTime'] = logout_time.isoformat() # Update logout time to the latest
            existing_today_entry['lastModified'] = datetime.now().isoformat()
            
            # Remove the now consolidated active entry
            time_entries.remove(active_entry)
            
            message = f'Thank you, {user["name"]}! Your hours for today have been updated.'
        else:
            # If no existing entry for today, just update the current active entry
            print(f"Log: Clocking out user '{user['name']}' (ID: {user_id}) for a new daily entry.")
            active_entry['logoutTime'] = logout_time.isoformat()
            active_entry['totalHours'] = current_session_hours
            active_entry['lastModified'] = datetime.now().isoformat()
            message = f'Thank you, {user["name"]}! You have been clocked out.'

        save_data(TIME_ENTRIES_FILE, time_entries)
        print(f"Log: User '{user['name']}' (ID: {user_id}) clocked out at {logout_time.isoformat()}. Total hours (this session): {current_session_hours}. Total for day (if consolidated): {existing_today_entry['totalHours'] if existing_today_entry else current_session_hours}.")
        return jsonify({'message': message}), 200
    else:
        print(f"Log: Clock-out failed for user '{user.get('name', 'N/A')}' (ID: {user_id}): No active clock-in found.")
        return jsonify({'message': 'No active clock-in found for this user.'}), 400

@app.route('/users', methods=['GET'])
def get_users():
    """Retrieves all users (for ADMIN/TIMEKEEPER)."""
    # Note: PINs are excluded for security. is_suspended is included.
    users_safe = []
    for user in users:
        user_copy = {k: v for k, v in user.items() if k != 'pin'}
        # Hydrate suspension notes for display
        user_copy['suspension_notes_full'] = [n for n in notes if n['id'] in user.get('suspension_notes', [])]
        users_safe.append(user_copy)

    print(f"Log: All users data requested. Total users: {len(users_safe)}.")
    return jsonify(users_safe), 200

@app.route('/users/add', methods=['POST'])
def add_user():
    """Adds a new user (ADMIN can add any role, TIMEKEEPER can only add 'worker')."""
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    role = data.get('role', 'worker')
    pin = data.get('pin')
    requester_role = data.get('requester_role')
    requester_name = data.get('requester_name')

    print(f"Log: User add request by '{requester_name}' (Role: {requester_role}) for new user '{name}' (Role: {role}).")

    if not name:
        print(f"Log: User add failed: Name is required.")
        return jsonify({'message': 'Name is required.'}), 400
    if not pin or not isinstance(pin, str) or not pin.isdigit():
        print(f"Log: User add failed for '{name}': PIN must be a non-empty number.")
        return jsonify({'message': 'PIN must be a non-empty number.'}), 400

    # Check PIN uniqueness for all roles
    if any(u.get('pin') == pin for u in users):
        print(f"Log: User add failed for '{name}': User with this PIN already exists.")
        return jsonify({'message': 'User with this PIN already exists.'}), 409

    # Authorization logic for adding users
    if requester_role == 'ADMIN':
        pass # ADMIN can add any role
    elif requester_role == 'TIMEKEEPER':
        if role != 'worker':
            print(f"Log: User add failed for '{name}': Timekeeper '{requester_name}' attempted to add non-worker role '{role}'.")
            return jsonify({'message': 'Timekeepers can only add worker accounts.'}), 403
    else:
        print(f"Log: User add failed for '{name}': Unauthorized requester role '{requester_role}'.")
        return jsonify({'message': 'Unauthorized to add users.'}), 403

    # Check email uniqueness if provided and not None
    if email and any(u.get('email') == email for u in users if u.get('email') is not None):
        print(f"Log: User add failed for '{name}': User with this email already exists.")
        return jsonify({'message': 'User with this email already exists.'}), 409

    new_user = {
        'id': str(uuid.uuid4()),
        'name': name,
        'email': email if email else None,
        'phone': phone if phone else None,
        'role': role,
        'pin': pin,
        'createdAt': datetime.now().isoformat(),
        'is_suspended': False,
        'suspension_notes': [] # Initialize with empty list for note IDs
    }
    users.append(new_user)
    save_data(USERS_FILE, users)
    print(f"Log: User '{new_user['name']}' (ID: {new_user['id']}, Role: {new_user['role']}) added successfully by '{requester_name}'.")
    return jsonify({'message': 'User added successfully', 'user_id': new_user['id']}), 201

@app.route('/users/delete/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Deletes a user and their time entries (ADMIN only)."""
    global users, time_entries, notes

    user_to_delete = next((u for u in users if u['id'] == user_id), None)
    if not user_to_delete:
        print(f"Log: Delete user failed for user_id '{user_id}': User not found.")
        return jsonify({'message': 'User not found'}), 404

    # Retrieve requester_id from request (frontend must send it)
    data = request.get_json()
    requester_id = data.get('requester_id')
    requester_user = next((u for u in users if u['id'] == requester_id), None)

    print(f"Log: Delete user request by '{requester_user.get('name', 'N/A')}' (ID: {requester_id}) for user '{user_to_delete['name']}' (ID: {user_id}).")

    if not requester_user or requester_user['role'] != 'ADMIN':
        print(f"Log: Delete user failed: Unauthorized request by '{requester_user.get('name', 'N/A')}' (ID: {requester_id}).")
        return jsonify({'message': 'Unauthorized to delete users. Only ADMINs can delete users.'}), 403

    if user_to_delete['id'] == requester_id:
        print(f"Log: Delete user failed: ADMIN '{requester_user['name']}' attempted to delete their own account.")
        return jsonify({'message': 'ADMIN cannot delete their own account via this endpoint to prevent accidental lockout.'}), 403

    if user_to_delete['role'] == 'ADMIN':
        admin_count = sum(1 for u in users if u['role'] == 'ADMIN')
        if admin_count <= 1:
            print(f"Log: Delete user failed: Cannot delete the last ADMIN account.")
            return jsonify({'message': 'Cannot delete the last ADMIN account.'}), 403

    # Log before state
    print(f"Log: Deleting user '{user_to_delete['name']}' (ID: {user_id}). Current users count: {len(users)}. Current time entries count: {len(time_entries)}. Current notes count: {len(notes)}.")

    # Collect notes associated with this user's time entries or suspensions
    notes_to_delete_ids = set()
    for entry in time_entries:
        if entry['userId'] == user_id:
            notes_to_delete_ids.update(entry.get('editNotes', []))
    notes_to_delete_ids.update(user_to_delete.get('suspension_notes', []))

    # Remove user
    users = [u for u in users if u['id'] != user_id]
    save_data(USERS_FILE, users)

    # Remove associated time entries
    time_entries = [entry for entry in time_entries if entry['userId'] != user_id]
    save_data(TIME_ENTRIES_FILE, time_entries)

    # Remove associated notes
    notes = [note for note in notes if note['id'] not in notes_to_delete_ids]
    save_data(NOTES_FILE, notes)

    # Log after state
    print(f"Log: User '{user_to_delete['name']}' (ID: {user_id}) and associated time entries and notes deleted successfully. New users count: {len(users)}. New time entries count: {len(time_entries)}. New notes count: {len(notes)}.")
    return jsonify({'message': 'User and associated time entries deleted successfully'}), 200

@app.route('/logout', methods=['POST']) # Renamed from /force_logout
def logout():
    """Logs out a user (ADMIN/TIMEKEEPER only) with a note."""
    global time_entries, notes
    data = request.get_json()
    user_id = data.get('user_id')
    note_content = data.get('note', 'Logged out by administrator/timekeeper.') # Default note
    requester_id = data.get('requester_id') # ID of the ADMIN/TIMEKEEPER forcing logout

    requester_user = next((u for u in users if u['id'] == requester_id), None)
    if not requester_user or requester_user['role'] not in ['ADMIN', 'TIMEKEEPER']:
        print(f"Log: Logout failed for user_id '{user_id}': Unauthorized request by '{requester_user.get('name', 'N/A')}' (ID: {requester_id}).")
        return jsonify({'message': 'Unauthorized to logout users.'}), 403

    user_to_logout = next((u for u in users if u['id'] == user_id), None)
    if not user_to_logout:
        print(f"Log: Logout failed for user_id '{user_id}': User not found.")
        return jsonify({'message': 'User not found.'}), 404

    active_entry = next((entry for entry in time_entries if entry['userId'] == user_id and entry['logoutTime'] is None), None)

    if active_entry:
        login_time = datetime.fromisoformat(active_entry['loginTime'])
        logout_time = datetime.now()
        duration = logout_time - login_time
        total_hours = round(duration.total_seconds() / 3600, 2)

        # Before state for the note
        before_state = {
            'loginTime': active_entry.get('loginTime'),
            'logoutTime': active_entry.get('logoutTime'),
            'totalHours': active_entry.get('totalHours')
        }

        # Update the entry
        active_entry['logoutTime'] = logout_time.isoformat()
        active_entry['totalHours'] = total_hours
        active_entry['edited'] = True
        active_entry['lastModified'] = datetime.now().isoformat()

        # After state for the note
        after_state = {
            'loginTime': active_entry.get('loginTime'),
            'logoutTime': active_entry.get('logoutTime'),
            'totalHours': active_entry.get('totalHours')
        }

        # Create and save the new note
        new_note_id = str(uuid.uuid4())
        new_note_content = (
            f"Logged out by {requester_user['name']}. Reason: {note_content}\n"
            f"Before:\n"
            f"  Clock In: {format_time_for_log(before_state['loginTime'])}\n"
            f"  Clock Out: {format_time_for_log(before_state['logoutTime'])}\n"
            f"  Hours: {before_state['totalHours']}\n"
            f"After:\n"
            f"  Clock In: {format_time_for_log(after_state['loginTime'])}\n"
            f"  Clock Out: {format_time_for_log(after_state['logoutTime'])}\n"
            f"  Hours: {after_state['totalHours']}"
        )

        new_note = {
            'id': new_note_id,
            'entityId': active_entry['id'],
            'entityType': 'time_entry',
            'timestamp': datetime.now().isoformat(),
            'editor': requester_user['name'],
            'note': new_note_content
        }
        notes.append(new_note)
        save_data(NOTES_FILE, notes)

        if 'editNotes' not in active_entry:
            active_entry['editNotes'] = []
        active_entry['editNotes'].append(new_note_id)
        save_data(TIME_ENTRIES_FILE, time_entries)

        print(f"Log: User '{user_to_logout['name']}' (ID: {user_id}) successfully logged out by '{requester_user['name']}'.")
        return jsonify({'message': f'{user_to_logout["name"]} has been successfully logged out.'}), 200
    else:
        print(f"Log: Logout failed for '{user_to_logout['name']}' (ID: {user_id}): Not currently clocked in.")
        return jsonify({'message': f'{user_to_logout["name"]} is not currently clocked in.'}), 400


@app.route('/edit_time_entry', methods=['POST'])
def edit_time_entry():
    """
    Edits a specific time entry for a worker (ADMIN/TIMEKEEPER only).
    Allows modification of loginTime, logoutTime, and adds a note.
    """
    global time_entries, notes
    data = request.get_json()
    entry_id = data.get('entry_id')
    new_login_time_str = data.get('login_time')
    new_logout_time_str = data.get('logout_time')
    edit_note_content = data.get('edit_note')
    editor_user_id = data.get('editor_user_id') # ID of the ADMIN/TIMEKEEPER making the edit

    if not entry_id or not edit_note_content:
        print(f"Log: Edit time entry failed: Entry ID and edit note are required. Entry ID: {entry_id}, Note: {edit_note_content}")
        return jsonify({'message': 'Entry ID and edit note are required.'}), 400

    entry_to_edit = next((entry for entry in time_entries if entry['id'] == entry_id), None)

    if not entry_to_edit:
        print(f"Log: Edit time entry failed for entry_id '{entry_id}': Time entry not found.")
        return jsonify({'message': 'Time entry not found.'}), 404

    editor_user = next((u for u in users if u['id'] == editor_user_id), None)
    if not editor_user or editor_user['role'] not in ['ADMIN', 'TIMEKEEPER']:
        print(f"Log: Edit time entry failed for entry_id '{entry_id}': Unauthorized request by '{editor_user.get('name', 'N/A')}' (ID: {editor_user_id}).")
        return jsonify({'message': 'Unauthorized to edit time entries.'}), 403

    # Capture before state
    before_login_time = entry_to_edit.get('loginTime')
    before_logout_time = entry_to_edit.get('logoutTime')
    before_total_hours = entry_to_edit.get('totalHours')

    try:
        # Parse new times
        login_dt = datetime.fromisoformat(new_login_time_str)
        logout_dt = datetime.fromisoformat(new_logout_time_str) if new_logout_time_str else None

        if logout_dt and logout_dt < login_dt:
            print(f"Log: Edit time entry failed for entry_id '{entry_id}': Logout time ({logout_dt}) cannot be before login time ({login_dt}).")
            return jsonify({'message': 'Logout time cannot be before login time.'}), 400

        # Update the entry
        entry_to_edit['loginTime'] = login_dt.isoformat()
        entry_to_edit['logoutTime'] = logout_dt.isoformat() if logout_dt else None

        if logout_dt:
            duration = logout_dt - login_dt
            entry_to_edit['totalHours'] = round(duration.total_seconds() / 3600, 2)
        else:
            entry_to_edit['totalHours'] = 0 # Or keep as None if still active

        entry_to_edit['edited'] = True
        entry_to_edit['lastModified'] = datetime.now().isoformat()

        # Capture after state
        after_login_time = entry_to_edit.get('loginTime')
        after_logout_time = entry_to_edit.get('logoutTime')
        after_total_hours = entry_to_edit.get('totalHours')

        # Create and save the new note with before/after details
        new_note_id = str(uuid.uuid4())
        new_note_content = (
            f"Edited by {editor_user['name']}. Reason: {edit_note_content}\n"
            f"Before:\n"
            f"  Clock In: {format_time_for_log(before_login_time)}\n"
            f"  Clock Out: {format_time_for_log(before_logout_time)}\n"
            f"  Hours: {before_total_hours}\n"
            f"After:\n"
            f"  Clock In: {format_time_for_log(after_login_time)}\n"
            f"  Clock Out: {format_time_for_log(after_logout_time)}\n"
            f"  Hours: {after_total_hours}"
        )

        new_note = {
            'id': new_note_id,
            'entityId': entry_id,
            'entityType': 'time_entry',
            'timestamp': datetime.now().isoformat(),
            'editor': editor_user['name'],
            'note': new_note_content
        }
        notes.append(new_note)
        save_data(NOTES_FILE, notes)

        if 'editNotes' not in entry_to_edit:
            entry_to_edit['editNotes'] = []
        entry_to_edit['editNotes'].append(new_note_id)

        save_data(TIME_ENTRIES_FILE, time_entries)
        print(f"Log: Time entry '{entry_id}' updated successfully by '{editor_user['name']}'.")
        return jsonify({'message': 'Time entry updated successfully!'}), 200

    except ValueError as e:
        print(f"Log: Edit time entry failed for entry_id '{entry_id}': Invalid date format - {e}.")
        return jsonify({'message': f'Invalid date format: {e}'}), 400
    except Exception as e:
        print(f"Log: Error editing time entry '{entry_id}': {e}.")
        return jsonify({'message': f'Error editing time entry: {e}'}), 500

def format_time_for_log(iso_string):
    """Formats an ISO time string for logging."""
    if iso_string:
        return datetime.fromisoformat(iso_string).strftime('%Y-%m-%d %H:%M')
    return 'N/A'


@app.route('/time_entries', methods=['GET'])
def get_all_time_entries():
    """Retrieves all time entries from all users (for ADMIN/TIMEKEEPER)."""
    # For displaying user names in the admin panel, we'll join with user data
    entries_with_names = []
    current_time = datetime.now()
    updated_entries_flag = False

    for entry in time_entries:
        entry_copy = entry.copy() # Avoid modifying original entry in list

        # Check and reset 'edited' flag if lastModified is older than 3 days
        if entry_copy.get('edited', False) and entry_copy.get('lastModified'):
            last_mod_dt = datetime.fromisoformat(entry_copy['lastModified'])
            if (current_time - last_mod_dt) > timedelta(days=3):
                entry_copy['edited'] = False
                updated_entries_flag = True

        user = next((u for u in users if u['id'] == entry['userId']), None)
        entry_copy['userName'] = user['name'] if user else 'Unknown User'

        # Hydrate notes for display in frontend
        entry_copy['editNotesFull'] = [n for n in notes if n['id'] in entry.get('editNotes', [])]
        entries_with_names.append(entry_copy)

    if updated_entries_flag:
        save_data(TIME_ENTRIES_FILE, time_entries) # Save if any 'edited' flags were reset
        print("Log: Reset 'edited' flags for time entries older than 3 days.")

    print(f"Log: All time entries data requested. Total entries: {len(entries_with_names)}.")
    return jsonify(entries_with_names), 200

@app.route('/suspend_user', methods=['POST'])
def suspend_user():
    """Suspends or Unsuspends a user (ADMIN/TIMEKEEPER only) with a note."""
    global users, notes
    data = request.get_json()
    user_id = data.get('user_id')
    is_suspended = data.get('is_suspended') # boolean: True to suspend, False to unsuspend
    note_content = data.get('note')
    requester_id = data.get('requester_id')

    requester_user = next((u for u in users if u['id'] == requester_id), None)
    user_to_modify = next((u for u in users if u['id'] == user_id), None)

    if not user_to_modify:
        print(f"Log: Suspension attempt failed for user_id '{user_id}': User not found.")
        return jsonify({'message': 'User not found.'}), 404

    if not requester_user or requester_user['role'] not in ['ADMIN', 'TIMEKEEPER']:
        print(f"Log: Suspension attempt failed for user '{user_to_modify.get('name', 'N/A')}: Unauthorized request by '{requester_user.get('name', 'N/A')}' (ID: {requester_id}).")
        return jsonify({'message': 'Unauthorized to suspend/unsuspend users.'}), 403

    if user_id == requester_id:
        print(f"Log: Suspension attempt failed for user '{user_id}': Cannot suspend/unsuspend self.")
        return jsonify({'message': 'Cannot suspend or unsuspend your own account.'}), 403

    # Timekeeper cannot suspend Admin
    if requester_user['role'] == 'TIMEKEEPER' and user_to_modify['role'] == 'ADMIN':
        print(f"Log: Suspension attempt failed: Timekeeper '{requester_user['name']}' tried to suspend Admin '{user_to_modify['name']}'.")
        return jsonify({'message': 'Timekeepers cannot suspend Admin accounts.'}), 403

    if not note_content or not note_content.strip():
        print(f"Log: Suspension attempt failed for user '{user_to_modify.get('name', 'N/A')}: A note is required for suspension/unsuspension.")
        return jsonify({'message': 'A note is required for suspension/unsuspension.'}), 400

    old_status = user_to_modify.get('is_suspended', False)
    action = "Suspended" if is_suspended else "Unsuspended"

    # Capture before state for note
    before_suspension_status = user_to_modify.get('is_suspended', False)
    before_role = user_to_modify.get('role')

    user_to_modify['is_suspended'] = is_suspended

    # Capture after state for note
    after_suspension_status = user_to_modify.get('is_suspended')
    after_role = user_to_modify.get('role') # Role might not change, but good to include for completeness

    # Create and save the new note with before/after details
    new_note_id = str(uuid.uuid4())
    new_note_content = (
        f"{action} by {requester_user['name']}. Reason: {note_content}\n"
        f"Before: Suspended: {before_suspension_status}, Role: {before_role}\n"
        f"After: Suspended: {after_suspension_status}, Role: {after_role}"
    )

    new_note = {
        'id': new_note_id,
        'entityId': user_id,
        'entityType': 'user_suspension',
        'timestamp': datetime.now().isoformat(),
        'editor': requester_user['name'],
        'note': new_note_content
    }
    notes.append(new_note)
    save_data(NOTES_FILE, notes)

    if 'suspension_notes' not in user_to_modify:
        user_to_modify['suspension_notes'] = []
    user_to_modify['suspension_notes'].append(new_note_id)
    save_data(USERS_FILE, users)

    print(f"Log: User '{user_to_modify['name']}' (ID: {user_id}) successfully {action.lower()} by '{requester_user['name']}'.")
    return jsonify({'message': f'User {user_to_modify["name"]} has been {action.lower()} successfully.'}), 200

@app.route('/notes/<note_id>', methods=['GET'])
def get_note(note_id):
    """Retrieves a single note by its ID."""
    note = next((n for n in notes if n['id'] == note_id), None)
    if note:
        return jsonify(note), 200
    return jsonify({'message': 'Note not found.'}), 404

@app.route('/notes/entity/<entity_id>', methods=['GET'])
def get_notes_for_entity(entity_id):
    """Retrieves all notes associated with a given entity (user or time entry)."""
    entity_notes = [n for n in notes if n.get('entityId') == entity_id]
    if entity_notes:
        # Sort notes by timestamp for chronological display
        entity_notes.sort(key=lambda x: datetime.fromisoformat(x['timestamp']))
        return jsonify(entity_notes), 200
    return jsonify([]), 200 # Return empty list if no notes found for entity


if __name__ == '__main__':
    app.run(debug=True)