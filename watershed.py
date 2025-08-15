import json
import time
import os
from datetime import datetime
from gpiozero import PWMOutputDevice, Button

CONFIG_FILE = "config.json"

def load_config():
    """Load config from JSON file."""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

def time_in_range(start_str, end_str, now):
    """Check if current time is within start/end range."""
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    if start < end:
        return start <= now <= end
    else:  # crosses midnight
        return now >= start or now <= end

def fade_pwm(device, start_val, end_val, fade_time):
    """Fade PWM value from start_val to end_val over fade_time seconds."""
    steps = 50
    step_delay = fade_time / steps
    for i in range(steps + 1):
        val = start_val + (end_val - start_val) * (i / steps)
        device.value = val
        time.sleep(step_delay)

def shutdown_pi():
    """Shutdown Raspberry Pi."""
    print("Shutdown button pressed. Shutting down now...")
    os.system("sudo halt")

def main():
    config = load_config()
    pump = PWMOutputDevice(config.get("pump_pin", 18), frequency=1000)

    # Shutdown button on GPIO 3 (BCM numbering), active low
    shutdown_button = Button(3, pull_up=True, bounce_time=0.1)
    shutdown_button.when_pressed = shutdown_pi

    last_config_check = 0

    while True:
        now = datetime.now()
        current_time = now.time()
        current_day = now.strftime("%a")

        # Reload config every 10 seconds
        if (time.time() - last_config_check) >= 10:
            config = load_config()
            last_config_check = time.time()

        if not config.get("enabled", True):
            pump.value = 0
            time.sleep(1)
            continue

        if current_day in config.get("active_days", []) and \
           time_in_range(config.get("start_time", "00:00"), config.get("end_time", "23:59"), current_time):

            interval = config.get("interval_ms", 5000) / 1000.0
            fade_time = config.get("fade_time_ms", 1000) / 1000.0
            on_duration = config.get("on_duration_ms", 2000) / 1000.0
            min_speed = config.get("pump_speed_min", 0.0)
            max_speed = config.get("pump_speed_max", 1.0)

            # Fade in
            fade_pwm(pump, min_speed, max_speed, fade_time)

            # Stay on at max speed for set duration
            time.sleep(on_duration)

            # Fade out
            fade_pwm(pump, max_speed, min_speed, fade_time)

            # Wait until next interval
            time.sleep(max(0, interval - (fade_time * 2 + on_duration)))
        else:
            pump.value = 0
            time.sleep(5)

if __name__ == "__main__":
    main()
