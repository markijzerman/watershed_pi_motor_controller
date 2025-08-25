import json
import time
import os
import threading
from datetime import datetime
from gpiozero import PWMOutputDevice, Button
from flask import Flask, render_template, request, jsonify
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CONFIG_FILE = "config.json"
config = {}   # shared config dict
config_lock = threading.Lock()

# -----------------------
# Config management
# -----------------------
def load_config():
    global config
    try:
        with open(CONFIG_FILE, "r") as f:
            new_config = json.load(f)
        # Ensure numeric types
        int_fields = ["interval_ms", "on_duration_ms", "fade_time_ms"]
        float_fields = ["pump_speed_min", "pump_speed_max"]
        for k in int_fields:
            if k in new_config:
                new_config[k] = int(new_config[k])
        for k in float_fields:
            if k in new_config:
                new_config[k] = float(new_config[k])
        # Ensure active_days is list
        if "active_days" in new_config and isinstance(new_config["active_days"], str):
            new_config["active_days"] = [d.strip() for d in new_config["active_days"].split(",") if d.strip()]

        with config_lock:
            config = new_config
        print("Config reloaded:", config)
    except Exception as e:
        print(f"Error loading config: {e}")

def save_config(new_config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(new_config, f, indent=4)

# -----------------------
# Watchdog handler
# -----------------------
class ConfigHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(CONFIG_FILE):
            load_config()

# -----------------------
# Pump logic
# -----------------------
def time_in_range(start_str, end_str, now):
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    if start < end:
        return start <= now <= end
    else:  # crosses midnight
        return now >= start or now <= end

def fade_pwm(device, start_val, end_val, fade_time):
    steps = 50
    step_delay = fade_time / steps if steps else fade_time
    for i in range(steps + 1):
        val = start_val + (end_val - start_val) * (i / steps)
        device.value = val
        time.sleep(step_delay)

def shutdown_pi():
    print("Shutdown button pressed. Shutting down now...")
    os.system("sudo halt")

def pump_loop():
    global config
    pump_pin = 18
    pump = PWMOutputDevice(pump_pin, frequency=1000)

    shutdown_button = Button(3, pull_up=True, bounce_time=0.1)
    shutdown_button.when_pressed = shutdown_pi

    while True:
        with config_lock:
            cfg = config.copy()

        now = datetime.now()
        current_time = now.time()
        current_day = now.strftime("%a")

        # Pump settings
        interval = float(cfg.get("interval_ms", 5000)) / 1000.0
        fade_time = float(cfg.get("fade_time_ms", 1000)) / 1000.0
        on_duration = float(cfg.get("on_duration_ms", 2000)) / 1000.0
        min_speed = float(cfg.get("pump_speed_min", 0.0))
        max_speed = float(cfg.get("pump_speed_max", 1.0))

        # Determine whether to run pump
        schedule_active = (current_day in cfg.get("active_days", [])) and \
                          time_in_range(cfg.get("start_time", "00:00"), cfg.get("end_time", "23:59"), current_time)
        manual_override = cfg.get("manual_on", False)

        if cfg.get("enabled", True) and (schedule_active or manual_override):
            # Run pump cycle exactly like scheduled, even in manual
            fade_pwm(pump, min_speed, max_speed, fade_time)
            time.sleep(on_duration)
            fade_pwm(pump, max_speed, min_speed, fade_time)
            # Wait until next interval
            time.sleep(max(0, interval - (fade_time * 2 + on_duration)))
        else:
            pump.value = 0
            time.sleep(0.5)

# -----------------------
# Flask Web Interface
# -----------------------
app = Flask(__name__)

@app.route("/")
def index():
    with config_lock:
        cfg = config.copy()
    return render_template("index.html", config=cfg)

@app.route("/update", methods=["POST"])
def update_config():
    new_config = request.json

    # Convert numeric fields
    int_fields = ["interval_ms", "on_duration_ms", "fade_time_ms"]
    float_fields = ["pump_speed_min", "pump_speed_max"]
    for k in int_fields:
        if k in new_config:
            try:
                new_config[k] = int(new_config[k])
            except ValueError:
                new_config[k] = 0
    for k in float_fields:
        if k in new_config:
            try:
                new_config[k] = float(new_config[k])
            except ValueError:
                new_config[k] = 0.0

    # Active days
    if "active_days" in new_config and isinstance(new_config["active_days"], str):
        new_config["active_days"] = [d.strip() for d in new_config["active_days"].split(",") if d.strip()]

    save_config(new_config)
    return jsonify({"status": "ok"})

@app.route("/toggle", methods=["POST"])
def toggle_pump():
    with config_lock:
        cfg = config.copy()
    cfg["manual_on"] = not cfg.get("manual_on", False)
    cfg["enabled"] = True  # ensure pump is enabled
    save_config(cfg)
    return jsonify({"manual_on": cfg["manual_on"], "enabled": cfg["enabled"]})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    threading.Thread(target=shutdown_pi).start()
    return jsonify({"status": "shutting down"})

# -----------------------
# Main entry
# -----------------------
def start_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    load_config()

    # Start watchdog
    event_handler = ConfigHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=False)
    observer.start()

    # Start pump loop
    t = threading.Thread(target=pump_loop, daemon=True)
    t.start()

    try:
        start_flask()
    finally:
        observer.stop()
        observer.join()
