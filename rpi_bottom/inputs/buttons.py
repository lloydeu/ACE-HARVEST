"""Button Input Handler"""
import RPi.GPIO as GPIO
import time
from config import *

class ButtonInput:
    """Handle all GPIO buttons with debouncing"""
    
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup all buttons with pullup
        GPIO.setup(PIN_EMERGENCY_STOP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BUTTON_START, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BUTTON_STOP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BUTTON_WINCH_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BUTTON_WINCH_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        self.button_states = {}
        self.last_press_time = {}
        self.debounce_time = 0.2
    
    def read(self):
        """Read all buttons, return list of events"""
        events = []
        current_time = time.time()
        
        # Check emergency stop (continuous check)
        if GPIO.input(PIN_EMERGENCY_STOP) == GPIO.LOW:
            if not self.button_states.get('emergency_stop', False):
                self.button_states['emergency_stop'] = True
                events.append({'type': 'emergency_stop'})
        else:
            self.button_states['emergency_stop'] = False
        
        # Check other buttons (edge detect)
        buttons = [
            (PIN_BUTTON_START, 'button_start'),
            (PIN_BUTTON_STOP, 'button_stop'),
            (PIN_BUTTON_WINCH_UP, 'winch_up'),
            (PIN_BUTTON_WINCH_DOWN, 'winch_down'),
        ]
        
        for pin, name in buttons:
            pressed = GPIO.input(pin) == GPIO.LOW
            was_pressed = self.button_states.get(name, False)
            
            if pressed and not was_pressed:
                # Button just pressed
                if name not in self.last_press_time or (current_time - self.last_press_time[name]) > self.debounce_time:
                    events.append({'type': name})
                    self.last_press_time[name] = current_time
            
            self.button_states[name] = pressed
        
        return events
    
    def cleanup(self):
        GPIO.cleanup()
