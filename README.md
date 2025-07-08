# WorkTrack-Pro

A full-stack time tracking and user management system built with Flask (Python backend) and a responsive HTML/CSS/JS frontend. Users can clock in/out with a PIN, and admins/timekeepers can manage users, suspend accounts, and edit time entries.

## 🔧 Features

- PIN-based login for all users
- Clock in/out system with session tracking
- Admin and Timekeeper dashboard
- User management (add/delete/suspend)
- Editable time entries with audit notes
- View past sessions and edit logs
- Role-based access control (ADMIN, TIMEKEEPER, WORKER)

## 🚀 Running the Project

1. **Backend**:
   - Python 3.8+
   - Run `python app.py` to start the Flask server (default: `http://127.0.0.1:5000`)

2. **Frontend**:
   - Open `index.html` in a browser
   - Make sure it points to your backend URL in the `API_BASE_URL`

## 📁 File Structure

```
app.py           # Flask backend with full API
index.html       # Frontend interface
users.json       # User data (generated)
time_entries.json# Time tracking data (generated)
notes.json       # Edit logs and suspension notes (generated)
```

## ⚠️ License & Usage

This project is owned by `jlaiii`.

![Alt Text](https://i.imgur.com/T3g8Ize.gif)
![Alt Text](https://i.imgur.com/hFAg9zd.gif)
