from flask import Flask, render_template, jsonify, request, send_from_directory
import os
from datetime import datetime
from pymongo import MongoClient
from transcript import audio2vec
from speech import process_emergency_call
from pathlib import Path
import json

app = Flask(__name__)

# Register Jinja filter for basename
@app.template_filter('basename')
def basename_filter(value):
    if not value:
        return ""
    return Path(value).name

# MongoDB
client = MongoClient("mongodb://localhost:27017/shake_detector")
db = client.shake_detector
emergencies = db.emergencies

# Uploads & static serving
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

DEFAULT_EMAIL = "tester@gmail.com"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/emergency", methods=["POST"])
def emergency_alert():
    form = request.form
    files = request.files

    # Safe JSON parsing
    try:
        location = json.loads(form.get("location", "{}") or "{}")
    except json.JSONDecodeError:
        location = {}

    try:
        device_info = json.loads(form.get("device_info", "{}") or "{}")
    except json.JSONDecodeError:
        device_info = {}

    audio_file = files.get('audio')
    photo_file = files.get('photo')

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    audio_path = photo_path = transcription = call_text = call_audio_path = None

    if audio_file:
        audio_path = os.path.join(UPLOAD_FOLDER, f"emergency_audio_{timestamp}.webm")
        audio_file.save(audio_path)
        transcription = audio2vec(audio_path)

    if photo_file:
        photo_path = os.path.join(UPLOAD_FOLDER, f"emergency_{timestamp}.png")
        photo_file.save(photo_path)

    # Generate emergency call audio
    try:
        if photo_path:
            call_text, call_audio_path_obj = process_emergency_call(
                image_path=photo_path,
                transcription=transcription,
                voice="austin"
            )
            call_audio_path = str(call_audio_path_obj)
    except Exception as e:
        print(f"Call audio generation failed: {e}")

    emergency = {
        "user_email": DEFAULT_EMAIL,
        "location": location,
        "device_info": device_info,
        "audio_path": audio_path,
        "photo_path": photo_path,
        "transcription": transcription,
        "call_text": call_text,
        "call_audio_path": call_audio_path,
        "timestamp": datetime.utcnow(),
    }

    result = emergencies.insert_one(emergency)
    print(f"🚨 NEW ALERT: {emergency}")

    return jsonify({
        "status": "success",
        "transcription": transcription,
        "call_text": call_text,
        "call_audio_path": call_audio_path,
        "id": str(result.inserted_id)
    })

@app.route("/api/notifications", methods=["GET"])
def notifications():
    """Simple polling endpoint for new alerts"""
    last_id = request.args.get('last_id', type=int, default=0)

    # For simplicity, return latest 5 alerts (client can filter client-side)
    # In production use a numeric alert_id counter
    new_alerts = list(emergencies.find().sort("timestamp", -1).limit(5))

    for alert in new_alerts:
        alert["_id"] = str(alert["_id"])
        alert["timestamp"] = alert["timestamp"].isoformat()

    return jsonify({
        "alerts": new_alerts,
        "latest_timestamp": new_alerts[0]["timestamp"] if new_alerts else None
    })

@app.route("/dashboard")
def dashboard():
    raw_alerts = list(emergencies.find().sort("timestamp", -1))
    now = datetime.utcnow()

    alerts = []
    for raw in raw_alerts:
        ts = raw["timestamp"]
        delta = (now - ts).total_seconds() // 60
        time_ago = "just now" if delta < 1 else f"{int(delta)} min ago"

        dir_url = ""
        loc = raw.get("location", {})
        if "lat" in loc and "lng" in loc:
            dir_url = f"https://www.google.com/maps/dir/?api=1&destination={loc['lat']},{loc['lng']}&travelmode=driving"

        photo_filename = Path(raw.get("photo_path", "")).name if raw.get("photo_path") else ""
        call_audio_filename = Path(raw.get("call_audio_path", "")).name if raw.get("call_audio_path") else ""

        alerts.append({
            "timestamp_str": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "time_ago": time_ago,
            "is_new": delta <= 4,
            "user_email": raw.get("user_email", "unknown"),
            "location": loc,
            "device_info": str(raw.get("device_info", {})),
            "photo_filename": photo_filename,
            "transcription": raw.get("transcription", ""),
            "call_text": raw.get("call_text", ""),
            "call_audio_filename": call_audio_filename,
            "directions_url": dir_url,
        })

    return render_template("dashboard.html", alerts=alerts)

@app.route("/dashboard/clear", methods=["POST"])
def clear_alerts():
    cnt = emergencies.delete_many({}).deleted_count
    print(f"Cleared {cnt} alerts")
    return jsonify({"deleted": cnt})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5032)