from flask import Flask, render_template, Response, jsonify
import cv2
import mediapipe as mp
import numpy as np
import time
from datetime import datetime
import sqlite3
from contextlib import closing
import threading

app = Flask(__name__)

# إعداد قاعدة البيانات
def init_db():
    with closing(sqlite3.connect('focus_data.db')) as conn:
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    total_focus REAL DEFAULT 0,
                    total_unfocus REAL DEFAULT 0,
                    focus_percentage REAL DEFAULT 0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS focus_periods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration REAL,
                    type TEXT CHECK(type IN ('focus', 'unfocus')),
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
            ''')

init_db()

# إعدادات تتبع العين
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

mpFace = mp.solutions.face_mesh
face_mesh = mpFace.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.9,
    min_tracking_confidence=0.7
)

# حالة التتبع
eye_state = {
    'direction': 'CENTER',
    'warned': False,
    'tracking_active': False,
    'session_active': False
}

# إحصائيات الجلسة
session_stats = {
    'start_time': None,
    'last_update': None,
    'current_focus_start': None,
    'current_unfocus_start': None,
    'total_focus': 0,
    'total_unfocus': 0,
    'focus_percentage': 0,
    'focus_periods': []
}

# الكاميرا العالمية
camera = cv2.VideoCapture(0)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
            
        frame = cv2.flip(frame, 1)
        
        if eye_state['tracking_active']:
            frame = process_frame(frame)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def process_frame(frame):
    imgRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, c = frame.shape
    results = face_mesh.process(imgRGB)

    if results.multi_face_landmarks:
        points = np.array([np.multiply([p.x, p.y], [w, h]).astype(int)
                      for p in results.multi_face_landmarks[0].landmark])

        left_iris_center = calc_center(LEFT_IRIS, points, frame, True)
        right_iris_center = calc_center(RIGHT_IRIS, points, frame, True)

        left_eye_center = calc_center(LEFT_EYE, points, frame)
        right_eye_center = calc_center(RIGHT_EYE, points, frame)

        eye1 = eye_direction(left_iris_center, left_eye_center)
        eye2 = eye_direction(right_iris_center, right_eye_center)

        direction = eye1 if eye1 == eye2 else (eye1 if eye1 != "CENTER" else eye2)
        eye_state['direction'] = direction

        update_session_stats(direction)
    
    return frame

def update_session_stats(direction):
    now = time.time()
    
    if direction == "CENTER":
        if session_stats['current_unfocus_start'] is not None:
            unfocus_duration = now - session_stats['current_unfocus_start']
            session_stats['total_unfocus'] += unfocus_duration
            session_stats['focus_periods'].append({
                'start': session_stats['current_unfocus_start'],
                'end': now,
                'duration': unfocus_duration,
                'type': 'unfocus'
            })
            session_stats['current_unfocus_start'] = None
            
        if session_stats['current_focus_start'] is None:
            session_stats['current_focus_start'] = now
            
        if eye_state['warned']:
            eye_state['warned'] = False
            log_event("استعادة التركيز")
            
    else:
        if session_stats['current_focus_start'] is not None:
            focus_duration = now - session_stats['current_focus_start']
            session_stats['total_focus'] += focus_duration
            session_stats['focus_periods'].append({
                'start': session_stats['current_focus_start'],
                'end': now,
                'duration': focus_duration,
                'type': 'focus'
            })
            session_stats['current_focus_start'] = None
            
        if session_stats['current_unfocus_start'] is None:
            session_stats['current_unfocus_start'] = now
            
        if not eye_state['warned'] and (now - (session_stats['last_update'] or now)) > 2:
            warn(frame=None)
            eye_state['warned'] = True
            log_event("تحذير: فقدان التركيز")
    
    session_stats['last_update'] = now
    
    total_time = session_stats['total_focus'] + session_stats['total_unfocus']
    if total_time > 0:
        session_stats['focus_percentage'] = (session_stats['total_focus'] / total_time) * 100

def log_event(message):
    now = datetime.now()
    cur_time = now.strftime("%Y-%m-%d %H:%M:%S")
    with open("focus_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{cur_time}] {message}\n")

def save_session_to_db():
    with closing(sqlite3.connect('focus_data.db')) as conn:
        with conn:
            session_id = conn.execute('''
                INSERT INTO sessions (start_time, end_time, total_focus, total_unfocus, focus_percentage)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.fromtimestamp(session_stats['start_time']).isoformat(),
                datetime.now().isoformat(),
                session_stats['total_focus'],
                session_stats['total_unfocus'],
                session_stats['focus_percentage']
            )).lastrowid

            if session_stats['focus_periods']:
                conn.executemany('''
                    INSERT INTO focus_periods (session_id, start_time, end_time, duration, type)
                    VALUES (?, ?, ?, ?, ?)
                ''', [
                    (session_id,
                     datetime.fromtimestamp(p['start']).isoformat(),
                     datetime.fromtimestamp(p['end']).isoformat(),
                     p['duration'],
                     p['type'])
                    for p in session_stats['focus_periods']
                ])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_session')
def start_session():
    if not eye_state['session_active']:
        eye_state['session_active'] = True
        eye_state['tracking_active'] = True
        session_stats['start_time'] = time.time()
        session_stats['last_update'] = time.time()
        log_event("بدأت جلسة جديدة")
    return jsonify({'status': 'success', 'message': 'Session started'})

@app.route('/end_session')
def end_session():
    if eye_state['session_active']:
        now = time.time()
        if session_stats['current_focus_start'] is not None:
            focus_duration = now - session_stats['current_focus_start']
            session_stats['total_focus'] += focus_duration
            session_stats['focus_periods'].append({
                'start': session_stats['current_focus_start'],
                'end': now,
                'duration': focus_duration,
                'type': 'focus'
            })
        if session_stats['current_unfocus_start'] is not None:
            unfocus_duration = now - session_stats['current_unfocus_start']
            session_stats['total_unfocus'] += unfocus_duration
            session_stats['focus_periods'].append({
                'start': session_stats['current_unfocus_start'],
                'end': now,
                'duration': unfocus_duration,
                'type': 'unfocus'
            })
        
        save_session_to_db()
        log_event(f"انتهت الجلسة - إجمالي وقت التركيز: {format_duration(session_stats['total_focus'])}")
        log_event(f"إجمالي وقت عدم التركيز: {format_duration(session_stats['total_unfocus'])}")
        
        eye_state['session_active'] = False
        eye_state['tracking_active'] = False
        reset_session_stats()
    return jsonify({'status': 'success', 'message': 'Session ended'})

@app.route('/get_stats')
def get_stats():
    return jsonify(session_stats)

@app.route('/get_eye_state')
def get_eye_state():
    return jsonify(eye_state)

@app.route('/get_history')
def get_history():
    with closing(sqlite3.connect('focus_data.db')) as conn:
        sessions = conn.execute('''
            SELECT id, start_time, end_time, total_focus, total_unfocus, focus_percentage
            FROM sessions
            ORDER BY start_time DESC
            LIMIT 30
        ''').fetchall()

        history = []
        for session in sessions:
            periods = conn.execute('''
                SELECT type, duration
                FROM focus_periods
                WHERE session_id = ?
                ORDER BY start_time
            ''', (session[0],)).fetchall()
            
            history.append({
                'id': session[0],
                'date': session[1][:10],
                'start_time': session[1][11:16],
                'end_time': session[2][11:16] if session[2] else None,
                'total_focus': session[3],
                'total_unfocus': session[4],
                'focus_percentage': session[5],
                'periods': [{'type': p[0], 'duration': p[1]} for p in periods]
            })
    
    return jsonify(history)

def reset_session_stats():
    session_stats.update({
        'start_time': None,
        'last_update': None,
        'current_focus_start': None,
        'current_unfocus_start': None,
        'total_focus': 0,
        'total_unfocus': 0,
        'focus_percentage': 0,
        'focus_periods': []
    })

def calc_center(indexes, points, img, draw=False):
    (cx, cy), radius = cv2.minEnclosingCircle(points[indexes])
    center = np.array([cx, cy], dtype=np.int32)
    if draw:
        cv2.circle(img, center, int(radius), (0, 0, 255), 1, cv2.LINE_AA)
    return center

def eye_direction(iris_center, eye_center):
    if abs(iris_center[0] - eye_center[0]) < 5:
        return "CENTER"
    elif iris_center[0] - eye_center[0] < 0:
        return "LEFT"
    elif iris_center[0]-eye_center[0] > 0:
        return "RIGHT"

def warn(img=None):
    if img is not None:
        h, w, c = img.shape
        cv2.rectangle(img, (0,0), (w, h), (0, 0, 255), -1)
        cv2.putText(img, "!انتبه ركز في الشاشة", (w//4, h//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)

def format_duration(seconds):
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours} ساعة {minutes} دقيقة {seconds} ثانية"
    elif minutes > 0:
        return f"{minutes} دقيقة {seconds} ثانية"
    else:
        return f"{seconds} ثانية"

if __name__ == '__main__':
    app.run(debug=True, threaded=True)