from flask import Flask, render_template, jsonify, request
import os
from datetime import datetime
from pymongo import MongoClient
from transcript import audio2vec

app = Flask(__name__)

client = MongoClient("mongodb://localhost:27017/shake_detector")
db = client.shake_detector
emergencies = db.emergencies

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DEFAULT_EMAIL = "tester@gmail.com"

# Hard-coded security location (e.g., Bengaluru campus gate – replace with real)
SECURITY_LAT = 13.0219  # IISc example
SECURITY_LNG = 77.5671

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/emergency", methods=["POST"])
def emergency_alert():
    data = request.form.to_dict()
    location_str = data.get("location", "{}")
    device_info_str = data.get("device_info", "{}")

    audio_file = request.files.get('audio')
    photo_file = request.files.get('photo')

    audio_path = None
    photo_path = None
    transcription = ""

    if audio_file:
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], "emergency_audio.webm")
        audio_file.save(audio_path)
        print(f"Audio saved/overwritten: {audio_path}")
        transcription = audio2vec(audio_path)

    if photo_file:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], "emergency.png")
        photo_file.save(photo_path)
        print(f"Photo saved/overwritten: {photo_path}")

    emergency = {
        "user_email": DEFAULT_EMAIL,
        "location": eval(location_str) if location_str else {},
        "device_info": eval(device_info_str) if device_info_str else {},
        "audio_path": audio_path,
        "photo_path": photo_path,
        "transcription": transcription,
        "timestamp": datetime.utcnow(),
    }

    result = emergencies.insert_one(emergency)
    print(f"Emergency stored: {emergency}")

    return jsonify({
        "status": "success",
        "message": "Alert received",
        "transcription": transcription,
        "id": str(result.inserted_id),
    })

@app.route("/api/emergencies", methods=["GET"])
def get_emergencies():
    recent = list(emergencies.find().sort("timestamp", -1).limit(10))
    for e in recent:
        e["_id"] = str(e["_id"])
        e["timestamp"] = e["timestamp"].isoformat()
    return jsonify(recent)

# New dashboard route
@app.route("/dashboard")
def dashboard():
    alerts = list(emergencies.find().sort("timestamp", -1))
    for alert in alerts:
        alert["_id"] = str(alert["_id"])
        alert["timestamp"] = alert["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        # Maps path URL
        if "location" in alert and "lat" in alert["location"] and "lng" in alert["location"]:
            alert_loc_lat = alert["location"]["lat"]
            alert_loc_lng = alert["location"]["lng"]
            alert["directions_url"] = f"https://www.google.com/maps/dir/?api=1&origin={SECURITY_LAT},{SECURITY_LNG}&destination={alert_loc_lat},{alert_loc_lng}&travelmode=driving"
        else:
            alert["directions_url"] = ""
    return render_template("dashboard.html", alerts=alerts, security_lat=SECURITY_LAT, security_lng=SECURITY_LNG)

# ──────────────────────────────────────────────
# NEW: Clear alerts endpoint (for demo reset button)
# ──────────────────────────────────────────────

@app.route("/dashboard/clear", methods=["POST"])
def clear_alerts():
    result = emergencies.delete_many({})
    print(f"Cleared {result.deleted_count} alerts")
    return jsonify({"status": "success", "deleted": result.deleted_count})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5032)