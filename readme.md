# Watershed pump system
Code for the pump for the Watershed installation series.


## Setup
* Default the pins to pigpio: export GPIOZERO_PIN_FACTORY=pigpio
* Add this line to bashrc, see: https://gpiozero.readthedocs.io/en/stable/api_pins.html
* Run the watershed.py on startup, see https://forums.raspberrypi.com/viewtopic.php?t=343733
* Do sudo nano /lib/systemd/system/watershed.service , and later enable, start this script
* Set up Raspberry Pi Connect: https://www.raspberrypi.com/documentation/services/connect.html


## Hardware
**Pump wiring (low-side switching with MOSFET):**

- Pump +  to  12V PSU +
    
- Pump - to MOSFET Drain
    
- MOSFET IRLZ44N Source to PSU GND
    
- MOSFET Gate to PI GPIO (e.g., GPIO18) via ~100 ohm resistor
    
- 10k resistor from Gate to GND (pulldown)
    
- 1N4007 diode across the pump (cathode to +12V, anode to pump -)

For MOSFET pins, see:
https://www.google.com/url?sa=i&url=https%3A%2F%2Fwww.componentsinfo.com%2Firlz44n%2F&psig=AOvVaw0t_BNICvP1TCz1oGAkIsK8&ust=1755096297201000&source=images&cd=vfe&opi=89978449&ved=0CBIQjRxqFwoTCND7q6zBhY8DFQAAAAAdAAAAABAt
