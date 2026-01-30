from flask import Flask, render_template, jsonify, request, send_from_directory
import os
from datetime import datetime
from pymongo import MongoClient
from transcript import audio2vec
from speech import process_emergency_call
from pathlib import Path
import json

app = Flask(__name__)

# MongoDB
client = MongoClient("mongodb://localhost:27017/shake_detector")
db = client.shake_detector
emergencies = db.emergencies

# Uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DEFAULT_EMAIL = "tester@gmail.com"


@app.template_filter('basename')
def basename_filter(value):
    """Extract filename from path (used in templates)"""
    if not value:
        return ""
    return Path(value).name


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/emergency", methods=["POST"])
def emergency_alert():
    form = request.form
    files = request.files

    # Parse JSON safely
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

    # Save audio + transcribe
    if audio_file:
        audio_path = os.path.join(UPLOAD_FOLDER, f"emergency_audio_{timestamp}.webm")
        audio_file.save(audio_path)
        transcription = audio2vec(audio_path)

    # Save photo
    if photo_file:
        photo_path = os.path.join(UPLOAD_FOLDER, f"emergency_{timestamp}.png")
        photo_file.save(photo_path)

    # Generate call text + TTS if photo exists
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


@app.route("/api/notifications")
def notifications():
    """Server-Sent Events endpoint for real-time notifications"""
    def event_stream():
        last_id = request.args.get('last_id', 0, type=int)
        while True:
            # Get newest alert after last_id
            new_alerts = list(emergencies.find(
                {"_id": {"$gt": emergencies.find_one({"_id": {"$gte": last_id}})["_id"]}}
            ).sort("timestamp", -1).limit(1))
            
            if new_alerts:
                alert = new_alerts[0]
                yield f"data: {json.dumps({'type': 'new_alert', 'alert': alert})}\n\n"
            
            import time
            time.sleep(1)
    
    return app.response_class(event_stream(), mimetype="text/event-stream")


@app.route("/dashboard")
def dashboard():
    raw_alerts = list(emergencies.find().sort("timestamp", -1))
    now = datetime.utcnow()

    alerts = []
    for raw in raw_alerts:
        ts = raw["timestamp"]
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)

        delta_minutes = (now - ts).total_seconds() // 60
        time_ago = "just now" if delta_minutes < 1 else f"{int(delta_minutes)} min ago"

        loc = raw.get("location", {})
        dir_url = ""
        if "lat" in loc and "lng" in loc:
            dir_url = (
                "https://www.google.com/maps/dir/?api=1"
                f"&destination={loc['lat']},{loc['lng']}&travelmode=driving"
            )

        photo_path = raw.get("photo_path")
        call_audio_path = raw.get("call_audio_path")

        photo_filename = Path(photo_path).name if photo_path else None
        call_audio_filename = Path(call_audio_path).name if call_audio_path else None

        alerts.append({
            "timestamp_str": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "time_ago": time_ago,
            "user_email": raw.get("user_email", "unknown"),
            "location": loc,
            "device_info": str(raw.get("device_info", {})),
            "photo_path": photo_path,
            "photo_filename": photo_filename,
            "transcription": raw.get("transcription", "") or "",
            "call_text": raw.get("call_text", "") or "",
            "call_audio_path": call_audio_path,
            "call_audio_filename": call_audio_filename,
            "directions_url": dir_url,
            "is_new": (now - ts).total_seconds() < 60,
        })

    return render_template("dashboard.html", alerts=alerts)


@app.route("/dashboard/clear", methods=["POST"])
def clear_alerts():
    cnt = emergencies.delete_many({}).deleted_count
    print(f"Cleared {cnt} alerts")
    return jsonify({"deleted": cnt})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5032)
