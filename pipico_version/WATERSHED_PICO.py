import machine
from machine import Pin, PWM, Timer, WDT
import network
import json
import utime
import gc

# Install microdot first with: 
# import mip
# mip.install("microdot")

from microdot import Microdot, Response

# Motor driver pins
m1 = Pin(21, Pin.OUT)
m2 = Pin(20, Pin.OUT)
en1_pin = Pin(17, Pin.OUT)
# Create PWM object for speed control
en1_pwm = PWM(en1_pin)
en1_pwm.freq(1000)  # 1kHz PWM frequency

# Configuration file
CONFIG_FILE = 'pump_config.json'

# Default configuration
default_config = {
    'pump_on': True,
    'interval_ms': 30000,
    'on_duration_ms': 100,
    'fade_time_ms': 100,
    'max_speed': 0.5
}

# Current state
current_config = default_config.copy()
flush_mode = False
current_speed = 0.0
target_speed = 0.0
pump_running = False
last_pump_time = 0
fade_start_time = 0
fade_duration = 0
fade_start_speed = 0.0
last_state = None
cycle_start_time = 0



# Network configuration
SSID = 'watershed'
PASSWORD = 'watershed'

# LED indicator
led = Pin('LED', Pin.OUT)

# Watchdog (5 second timeout)
wdt = WDT(timeout=5000)

# Load configuration from file
def load_config():
    global current_config
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
            current_config.update(loaded)
            print(f"Config loaded: {current_config}")
    except:
        print("No config file found, using defaults")
        save_config()

# Save configuration to file
def save_config():
    try:
        save_data = current_config.copy()
        if 'flush_mode' in save_data:
            del save_data['flush_mode']
        with open(CONFIG_FILE, 'w') as f:
            json.dump(save_data, f)
        print("Config saved")
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Motor control functions
def set_motor_speed(speed):
    """Set motor speed (0.0 to 1.0)"""
    global current_speed
    speed = max(0.0, min(1.0, speed))
    current_speed = speed
    if speed > 0:
        m1.value(1)
        m2.value(0)
        en1_pwm.duty_u16(int(speed * 65535))
    else:
        m1.value(0)
        m2.value(0)
        en1_pwm.duty_u16(0)

def fade_to_speed(target, duration_ms):
    """Schedule fade to target speed over duration"""
    global target_speed, fade_start_time, fade_duration, fade_start_speed
    target_speed = max(0.0, min(1.0, target))
    fade_start_speed = current_speed
    fade_start_time = utime.ticks_ms()
    fade_duration = max(1, duration_ms)

# Main timer loop
main_timer = Timer()

def main_loop_tick(t):
    global pump_running, last_pump_time, current_speed, fade_duration
    global last_state, cycle_start_time

    now = utime.ticks_ms()

    # Feed watchdog
    wdt.feed()

    # Handle fade
    if fade_duration > 0:
        elapsed = utime.ticks_diff(now, fade_start_time)
        if elapsed >= fade_duration:
            set_motor_speed(target_speed)
            fade_duration = 0
        else:
            progress = elapsed / fade_duration
            new_speed = fade_start_speed + (target_speed - fade_start_speed) * progress
            set_motor_speed(new_speed)

    # Skip normal cycle if flush mode
    if flush_mode:
        if last_state != "flush":
            print("Flush mode active: Pump running continuously at full speed")
            last_state = "flush"
        return

    # Start pump cycle
    if current_config['pump_on']:
        if not pump_running and utime.ticks_diff(now, last_pump_time) >= current_config['interval_ms']:
            pump_running = True
            cycle_start_time = now
            fade_to_speed(current_config['max_speed'], current_config['fade_time_ms'])
            print("Pump fading in...")

    # Stop pump after on_duration_ms
    if pump_running and utime.ticks_diff(now, cycle_start_time) >= current_config['on_duration_ms']:
        fade_to_speed(0, current_config['fade_time_ms'])
        pump_running = False
        last_pump_time = now   # mark end of cycle for interval tracking
        print("Pump fading out...")
        last_state = None      # <-- allow "Waiting..." to be printed again


    # Waiting state
    if not pump_running and last_state != "waiting":
        print("Waiting for next cycle...")
        last_state = "waiting"


def setup_pump_timer():
    """Setup main loop timer"""
    main_timer.init(period=100, mode=Timer.PERIODIC, callback=main_loop_tick)

# Setup WiFi Access Point
def setup_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=SSID, password=PASSWORD)
    while not ap.active():
        utime.sleep(0.1)
    print('Access Point active')
    print('Network config:', ap.ifconfig())
    print(f'Connect to WiFi network: {SSID}')
    print(f'Password: {PASSWORD}')
    print('Then navigate to: http://192.168.4.1')
    return ap

# Initialize
load_config()
ap = setup_ap()
led.on()

# Create Microdot app
app = Microdot()

# HTML template
def get_html():
    status = "ON" if current_config['pump_on'] else "OFF"
    flush_status = "ON (ACTIVE)" if flush_mode else "OFF"
    flush_color = "#ff4444" if flush_mode else "#888"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Watershed Pump Control</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="10">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 25px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin: 0 0 30px 0;
                text-align: center;
                font-size: 28px;
            }}
            .card {{
                background: white;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            }}
            h2 {{
                color: #555;
                margin-top: 0;
                font-size: 20px;
                border-bottom: 2px solid #f0f0f0;
                padding-bottom: 10px;
            }}
            .control-group {{
                margin: 20px 0;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #e9ecef;
            }}
            label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #495057;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            input[type="number"] {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                box-sizing: border-box;
                font-size: 16px;
                transition: border-color 0.3s;
                background: white;
            }}
            input[type="number"]:focus {{
                outline: none;
                border-color: #667eea;
            }}
            button {{
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                margin: 5px;
                transition: all 0.3s;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            }}
            .btn-danger {{
                background: {flush_color};
                color: white;
                font-weight: bold;
                box-shadow: 0 4px 15px rgba(255, 68, 68, 0.3);
            }}
            .btn-save {{
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
                width: 100%;
                margin-top: 20px;
                padding: 14px;
                font-size: 18px;
                box-shadow: 0 4px 15px rgba(56, 239, 125, 0.4);
            }}
            .status {{
                display: inline-block;
                padding: 6px 12px;
                border-radius: 20px;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .status-on {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .status-off {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            .warning {{
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
                font-weight: 600;
                box-shadow: 0 4px 15px rgba(245, 87, 108, 0.3);
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
                100% {{ transform: scale(1); }}
            }}
            .info-text {{
                color: #6c757d;
                font-size: 12px;
                margin-top: 5px;
            }}
            .button-group {{
                display: flex;
                gap: 10px;
                justify-content: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Watershed Pump Control</h1>
            
            <div class="card">
                <h2>Main Controls</h2>
                <div class="control-group">
                    <label>Pump Status</label>
                    <div class="button-group">
                        <span class="status {'status-on' if current_config['pump_on'] else 'status-off'}">{status}</span>
                        <button class="btn-primary" onclick="togglePump()">
                            {'TURN OFF' if current_config['pump_on'] else 'TURN ON'}
                        </button>
                    </div>
                </div>
                
                <div class="control-group">
                    <label>Flush Mode</label>
                    <div class="button-group">
                        <span class="status" style="background: {flush_color}; color: white;">{flush_status}</span>
                        <button class="btn-danger" onclick="toggleFlush()">
                            {'STOP FLUSH' if flush_mode else 'START FLUSH'}
                        </button>
                    </div>
                    {'<div class="warning">FLUSH MODE ACTIVE - Pump running continuously at full speed!</div>' if flush_mode else ''}
                </div>
            </div>
            
            <div class="card">
                <h2>Pump Settings</h2>
                <form id="settingsForm">
                    <div class="control-group">
                        <label for="interval">Interval (ms)</label>
                        <input type="number" id="interval" value="{current_config['interval_ms']}" min="100" max="3600000">
                        <div class="info-text">Time between pump cycles</div>
                    </div>
                    
                    <div class="control-group">
                        <label for="duration">On Duration (ms)</label>
                        <input type="number" id="duration" value="{current_config['on_duration_ms']}" min="10" max="60000">
                        <div class="info-text">How long pump runs per cycle</div>
                    </div>
                    
                    <div class="control-group">
                        <label for="fade">Fade Time (ms)</label>
                        <input type="number" id="fade" value="{current_config['fade_time_ms']}" min="0" max="5000">
                        <div class="info-text">Speed ramp up/down time</div>
                    </div>
                    
                    <div class="control-group">
                        <label for="speed">Max Speed (0.0 - 1.0)</label>
                        <input type="number" id="speed" value="{current_config['max_speed']}" min="0" max="1" step="0.1">
                        <div class="info-text">Maximum pump speed during operation</div>
                    </div>
                    
                    <button type="button" class="btn-save" onclick="saveSettings()">SAVE SETTINGS</button>
                </form>
            </div>
            
            <div style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px;">
                Auto-refresh every 10 seconds | IP: 192.168.4.1
            </div>
        </div>
        
        <script>
            function togglePump() {{
                fetch('/api/toggle_pump', {{method: 'POST'}})
                    .then(() => location.reload())
                    .catch(err => alert('Error: ' + err));
            }}
            
            function toggleFlush() {{
                const msg = {('"Stop flush mode?"' if flush_mode else '"Start flush mode? This will run the pump continuously at full speed!"')};
                if (!confirm(msg)) return;
                fetch('/api/toggle_flush', {{method: 'POST'}})
                    .then(() => location.reload())
                    .catch(err => alert('Error: ' + err));
            }}
            
            function saveSettings() {{
                const settings = {{
                    interval_ms: parseInt(document.getElementById('interval').value),
                    on_duration_ms: parseInt(document.getElementById('duration').value),
                    fade_time_ms: parseInt(document.getElementById('fade').value),
                    max_speed: parseFloat(document.getElementById('speed').value)
                }};
                
                if (settings.max_speed < 0 || settings.max_speed > 1) {{
                    alert('Speed must be between 0.0 and 1.0');
                    return;
                }}
                
                fetch('/api/save', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(settings)
                }})
                .then(response => response.text())
                .then(result => {{
                    alert(result);
                    location.reload();
                }})
                .catch(err => alert('Error saving: ' + err));
            }}
        </script>
    </body>
    </html>
    """

# Routes
@app.route('/')
def index(request):
    return get_html(), 200, {'Content-Type': 'text/html'}

@app.route('/api/status')
def status(request):
    return json.dumps({
        'pump_on': current_config['pump_on'],
        'flush_mode': flush_mode,
        'config': current_config,
        'current_speed': current_speed,
        'pump_running': pump_running
    })

@app.route('/api/toggle_pump', methods=['POST'])
def toggle_pump(request):
    global current_config
    current_config['pump_on'] = not current_config['pump_on']
    if not current_config['pump_on']:
        set_motor_speed(0)
    setup_pump_timer()
    return 'OK'

@app.route('/api/toggle_flush', methods=['POST'])
def toggle_flush(request):
    global flush_mode
    flush_mode = not flush_mode
    if flush_mode:
        set_motor_speed(1.0)
    else:
        set_motor_speed(0)
        setup_pump_timer()
    return 'OK'

@app.route('/api/save', methods=['POST'])
def save_settings(request):
    global current_config
    try:
        new_settings = json.loads(request.body)
        if 'interval_ms' in new_settings:
            current_config['interval_ms'] = max(100, int(new_settings['interval_ms']))
        if 'on_duration_ms' in new_settings:
            current_config['on_duration_ms'] = max(10, int(new_settings['on_duration_ms']))
        if 'fade_time_ms' in new_settings:
            current_config['fade_time_ms'] = max(0, int(new_settings['fade_time_ms']))
        if 'max_speed' in new_settings:
            current_config['max_speed'] = max(0.0, min(1.0, float(new_settings['max_speed'])))
        if save_config():
            setup_pump_timer()
            return 'Settings saved successfully!'
        else:
            return 'Error saving settings', 500
    except Exception as e:
        print(f"Error in save_settings: {e}")
        return f'Error: {str(e)}', 400

@app.errorhandler(404)
def not_found(request):
    return 'Not found', 404

# Start pump timer
setup_pump_timer()

print("Starting Microdot server...")
print(f"Connect to WiFi: {SSID} with password: {PASSWORD}")
print("Then browse to: http://192.168.4.1")

try:
    app.run(host='0.0.0.0', port=80)
except KeyboardInterrupt:
    print("Server stopped")
    set_motor_speed(0)
    machine.reset()





