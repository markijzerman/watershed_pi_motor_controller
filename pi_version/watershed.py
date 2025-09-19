import json
import time
import os
import threading
from datetime import datetime
from gpiozero import PWMOutputDevice
from flask import Flask, request, jsonify, send_from_directory

CONFIG_FILE = "config.json"
config_lock = threading.Lock()
config = {}

app = Flask(__name__)

# ----------------------
# Default configuration
# ----------------------
DEFAULT_CONFIG = {
    "pump_pin": 18,
    "interval_ms": 5000,
    "on_duration_ms": 2000,
    "fade_time_ms": 1000,
    "pump_speed_min": 0.0,
    "pump_speed_max": 1.0,
    "start_time": "00:00",
    "end_time": "23:59",
    "active_days": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    "manual_on": False,
    "flush_on": False,
    "enabled": True
}

# ----------------------
# Config handling
# ----------------------
def load_config():
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}
        else:
            cfg = {}
    except Exception as e:
        print(f"Error loading config: {e}")
        cfg = {}

    # Start with defaults and update with loaded config
    updated = DEFAULT_CONFIG.copy()
    updated.update(cfg)

    with config_lock:
        config = updated

    # Save back the merged config to ensure file exists
    save_config(updated)
    print("Config loaded:", config)

def save_config(new_cfg):
    global config
    try:
        print(f"Attempting to save config: {new_cfg}")
        
        # Create a complete config with defaults
        complete_cfg = DEFAULT_CONFIG.copy()
        complete_cfg.update(new_cfg)
        
        # Write to a temporary file first
        temp_file = CONFIG_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(complete_cfg, f, indent=4)
            f.flush()  # Ensure data is written
            os.fsync(f.fileno())  # Force write to disk
        
        # Atomic rename (works on Unix systems)
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        os.rename(temp_file, CONFIG_FILE)
        
        with config_lock:
            config = complete_cfg.copy()
        
        print("Config saved successfully")
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        import traceback
        traceback.print_exc()
        # Clean up temp file if it exists
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except:
            pass
        return False

# ----------------------
# Helpers
# ----------------------
def time_in_range(start_str, end_str, now):
    try:
        start = datetime.strptime(start_str, "%H:%M").time()
        end = datetime.strptime(end_str, "%H:%M").time()
        if start < end:
            return start <= now <= end
        else:
            return now >= start or now <= end
    except Exception as e:
        print(f"Error checking time range: {e}")
        return False

def fade_pwm(device, start_val, end_val, fade_time):
    if fade_time <= 0:
        device.value = end_val
        return
        
    steps = max(10, int(fade_time * 50))  # At least 10 steps
    step_delay = fade_time / steps
    
    for i in range(steps + 1):
        val = start_val + (end_val - start_val) * (i / steps)
        val = max(0.0, min(1.0, val))  # Clamp between 0 and 1
        device.value = val
        time.sleep(step_delay)

# ----------------------
# Pump control loop
# ----------------------
def pump_loop():
    global config
    pump = None
    current_pin = None
    last_flush_state = False
    
    while True:
        try:
            with config_lock:
                cfg = config.copy()

            # Reinitialize pump if pin changed
            new_pin = cfg.get("pump_pin", 18)
            if current_pin != new_pin:
                if pump:
                    pump.close()
                try:
                    pump = PWMOutputDevice(new_pin, frequency=1000)
                    current_pin = new_pin
                    print(f"Pump initialized on pin {new_pin}")
                except Exception as e:
                    print(f"Error initializing pump on pin {new_pin}: {e}")
                    time.sleep(5)
                    continue

            if not pump:
                time.sleep(1)
                continue

            now = datetime.now()
            current_time = now.time()
            current_day = now.strftime("%a")

            interval = max(1.0, float(cfg.get("interval_ms", 5000)) / 1000.0)
            fade_time = max(0.0, float(cfg.get("fade_time_ms", 1000)) / 1000.0)
            on_duration = max(0.1, float(cfg.get("on_duration_ms", 2000)) / 1000.0)
            min_speed = max(0.0, min(1.0, float(cfg.get("pump_speed_min", 0.0))))
            max_speed = max(0.0, min(1.0, float(cfg.get("pump_speed_max", 1.0))))

            # Check if schedule should be active (only if system is enabled)
            schedule_active = False
            if cfg.get("enabled", True):
                schedule_active = (current_day in cfg.get("active_days", [])) and \
                                  time_in_range(cfg.get("start_time", "00:00"),
                                                cfg.get("end_time", "23:59"),
                                                current_time)
            
            manual_override = cfg.get("manual_on", False)
            flush_override = cfg.get("flush_on", False)

            # Handle flush mode
            if flush_override:
                # Only log state change
                if not last_flush_state:
                    print(f"Flush mode activated - pump at {max_speed}")
                    last_flush_state = True
                pump.value = max_speed
                time.sleep(0.5)
                continue
            else:
                # If we were in flush mode, log the exit
                if last_flush_state:
                    print("Flush mode deactivated")
                    last_flush_state = False

            # Handle normal operation
            if schedule_active or manual_override:
                # Calculate current pump speed if we need to fade
                current_speed = pump.value if pump else min_speed
                
                # Fade up from current speed
                fade_pwm(pump, current_speed, max_speed, fade_time)
                # Stay on
                time.sleep(on_duration)
                # Fade down
                fade_pwm(pump, max_speed, min_speed, fade_time)
                # Wait for rest of interval
                sleep_time = max(0.5, interval - (fade_time * 2 + on_duration))
                time.sleep(sleep_time)
            else:
                pump.value = min_speed
                time.sleep(0.5)
                
        except Exception as e:
            print(f"Error in pump control loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)

# ----------------------
# Flask routes
# ----------------------
@app.route("/")
def index():
    # Serve the static HTML file
    return send_from_directory('templates', 'index.html')

@app.route("/update", methods=["POST"])
def update_config():
    global config
    try:
        data = request.form.to_dict(flat=False)
        print("Raw form data received:", data)
        
        # Start with current config
        with config_lock:
            new_config = config.copy()
        
        # Process form data
        processed_data = {}
        
        # Handle regular fields
        for key, value_list in data.items():
            if key != "active_days":
                processed_data[key] = value_list[0] if value_list else ""
        
        # Handle active_days checkboxes
        if "active_days" in data:
            processed_data["active_days"] = data["active_days"]
        elif any(field in data for field in ["start_time", "end_time", "enabled"]):
            # Schedule form submitted with no days checked
            processed_data["active_days"] = []
            
        print("Processed form data:", processed_data)

        # Convert numeric fields
        for key in ["pump_pin", "interval_ms", "on_duration_ms", "fade_time_ms"]:
            if key in processed_data and processed_data[key]:
                try:
                    processed_data[key] = int(processed_data[key])
                except (ValueError, TypeError):
                    print(f"Invalid integer value for {key}: {processed_data[key]}")
                    del processed_data[key]

        for key in ["pump_speed_min", "pump_speed_max"]:
            if key in processed_data and processed_data[key]:
                try:
                    processed_data[key] = float(processed_data[key])
                except (ValueError, TypeError):
                    print(f"Invalid float value for {key}: {processed_data[key]}")
                    del processed_data[key]

        # Handle enabled checkbox
        if "enabled" in processed_data:
            processed_data["enabled"] = processed_data["enabled"].lower() in ["true", "1", "on", "yes"]
        elif "enabled" in data or "start_time" in data or "end_time" in data:
            # Schedule form submitted without enabled checked
            processed_data["enabled"] = False

        # Remove empty string values
        processed_data = {k: v for k, v in processed_data.items() if v != ""}
        print("Final processed data:", processed_data)

        # Update config with processed data
        new_config.update(processed_data)
        
        # Validate ranges
        if "pump_speed_min" in processed_data:
            new_config["pump_speed_min"] = max(0.0, min(1.0, new_config["pump_speed_min"]))
        if "pump_speed_max" in processed_data:
            new_config["pump_speed_max"] = max(0.0, min(1.0, new_config["pump_speed_max"]))
        if "interval_ms" in processed_data:
            new_config["interval_ms"] = max(1000, new_config["interval_ms"])
        if "on_duration_ms" in processed_data:
            new_config["on_duration_ms"] = max(100, new_config["on_duration_ms"])
        if "fade_time_ms" in processed_data:
            new_config["fade_time_ms"] = max(0, new_config["fade_time_ms"])
        
        print("Final config to save:", new_config)
        
        if save_config(new_config):
            return jsonify({"status": "success", "config": new_config})
        else:
            return jsonify({"status": "error", "message": "Failed to save config"}), 500
                
    except Exception as e:
        print(f"Error updating config: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/toggle", methods=["POST"])
def toggle_pump():
    global config
    try:
        with config_lock:
            cfg = config.copy()
        
        cfg["manual_on"] = not cfg.get("manual_on", False)
        print(f"Toggling manual pump to: {cfg['manual_on']}")
        
        if save_config(cfg):
            print("Manual pump toggle saved successfully")
            return jsonify({"status": "success", "manual_on": cfg["manual_on"]})
        else:
            print("Failed to save manual pump toggle")
            return jsonify({"status": "error", "message": "Failed to save config"}), 500
    except Exception as e:
        print(f"Error toggling pump: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/toggle_flush", methods=["POST"])
def toggle_flush():
    global config
    try:
        with config_lock:
            cfg = config.copy()
        
        cfg["flush_on"] = not cfg.get("flush_on", False)
        print(f"Toggling flush to: {cfg['flush_on']}")
        
        if save_config(cfg):
            print("Flush toggle saved successfully")
            return jsonify({"status": "success", "flush_on": cfg["flush_on"]})
        else:
            print("Failed to save flush toggle")
            return jsonify({"status": "error", "message": "Failed to save config"}), 500
    except Exception as e:
        print(f"Error toggling flush: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/shutdown", methods=["POST"])
def shutdown_pi_route():
    try:
        os.system("sudo halt")
        return jsonify({"status": "shutting down"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/test", methods=["GET", "POST"])
def test_endpoint():
    try:
        return jsonify({"status": "success", "message": "Server is responding", "method": request.method})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/status")
def get_status():
    try:
        with config_lock:
            cfg = config.copy()
        
        now = datetime.now()
        current_time = now.time()
        current_day = now.strftime("%a")
        
        # Schedule only active if system is enabled
        schedule_active = False
        if cfg.get("enabled", True):
            schedule_active = (current_day in cfg.get("active_days", [])) and \
                              time_in_range(cfg.get("start_time", "00:00"),
                                            cfg.get("end_time", "23:59"),
                                            current_time)
        
        manual_override = cfg.get("manual_on", False)
        flush_override = cfg.get("flush_on", False)
        
        # Pump is active if ANY of these are true (manual and flush work regardless of enabled)
        pump_active = schedule_active or manual_override or flush_override
        
        return jsonify({
            "pump_active": pump_active,
            "schedule_active": schedule_active,
            "manual_on": manual_override,
            "flush_on": flush_override,
            "current_time": current_time.strftime("%H:%M"),
            "current_day": current_day,
            "config": cfg
        })
    except Exception as e:
        print(f"Error in status endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------------
# Watchdog for external config changes
# ----------------------
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_reload = 0
        
    def on_modified(self, event):
        if event.src_path.endswith(CONFIG_FILE):
            # Debounce to avoid multiple reloads
            current_time = time.time()
            if current_time - self.last_reload > 1:
                print("Config file changed externally, reloading...")
                self.last_reload = current_time
                time.sleep(0.1)  # Small delay to ensure file is fully written
                load_config()

def start_watchdog():
    event_handler = ConfigEventHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=False)
    observer.start()
    return observer

# ----------------------
# Main
# ----------------------
if __name__ == "__main__":
    # Ensure templates directory exists
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("Created templates directory")
    
    # Load initial config
    load_config()
    
    # Start pump control thread
    pump_thread = threading.Thread(target=pump_loop, daemon=True)
    pump_thread.start()
    print("Pump control thread started")
    
    # Start file watchdog
    observer = start_watchdog()
    print("Config file watchdog started")
    
    try:
        print("Starting Flask server on port 5000...")
        app.run(host="0.0.0.0", port=5000, debug=False)
    finally:
        observer.stop()
        observer.join()
        print("Application stopped")
