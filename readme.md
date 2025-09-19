# Watershed pump system
Code for the pump for the Watershed installation series.
I first made a version to run on a Pi 4 with a specific HAT, and then made a version to run on a Pi Pico with the motor controller. The latter is better to use in a situation where the power is switched off in the building.
Pico W version still has to be tested properly as of 19-09-25.

## Pi Pico W + SB Components Motor Controller Version

### Setup
* Upload the code to the Pi Pico W main.py from Thonny, maybe install the microdot package.
* It can be tricky to get Thonny to 'recognize' the Pi Pico W, the trick is to click stop a few times until the 'Files' show up (check View>Files in Thonny).

### Hardware
Needed is:
- Pi Pico W
- SB Components Pico Motor Driver HAT - https://shop.sb-components.co.uk/products/pico-motor-driver
- 12V power supply
- Kamoer pump or similar


## Pi4 + Custom HAT version

### Setup
* Default the pins to pigpio: export GPIOZERO_PIN_FACTORY=pigpio
* Add this line to bashrc, see: https://gpiozero.readthedocs.io/en/stable/api_pins.html
* Run the watershed.py on startup, see https://forums.raspberrypi.com/viewtopic.php?t=343733
* Do sudo nano /lib/systemd/system/watershed.service , and later enable, start this script
* Set up Raspberry Pi Connect: https://www.raspberrypi.com/documentation/services/connect.html


### Hardware
**Pump wiring (low-side switching with MOSFET):**

- Pump +  to  12V PSU +
    
- Pump - to MOSFET Drain
    
- MOSFET IRLZ44N Source to PSU GND
    
- MOSFET Gate to PI GPIO (e.g., GPIO18) via ~100 ohm resistor
    
- 10k resistor from Gate to GND (pulldown)
    
- 1N4007 diode across the pump (cathode to +12V, anode to pump -)

For MOSFET pins, see:
https://www.google.com/url?sa=i&url=https%3A%2F%2Fwww.componentsinfo.com%2Firlz44n%2F&psig=AOvVaw0t_BNICvP1TCz1oGAkIsK8&ust=1755096297201000&source=images&cd=vfe&opi=89978449&ved=0CBIQjRxqFwoTCND7q6zBhY8DFQAAAAAdAAAAABAt

On my boards I added a button for shutdown, but this seemed very fiddly (not recognizing GPIO pins and the like...?)
