"""Winch Control Output"""
import RPi.GPIO as GPIO
import time
from config import PIN_WINCH_RELAY_FORWARD, PIN_WINCH_RELAY_REVERSE

class WinchOutput:
    """DC winch with 2 relays (forward/reverse)"""
    
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_WINCH_RELAY_FORWARD, GPIO.OUT)
        GPIO.setup(PIN_WINCH_RELAY_REVERSE, GPIO.OUT)
        self.stop()
    
    def forward(self):
        """Winch forward (up)"""
        GPIO.output(PIN_WINCH_RELAY_REVERSE, GPIO.LOW)
        time.sleep(0.05)  # Safety delay
        GPIO.output(PIN_WINCH_RELAY_FORWARD, GPIO.HIGH)
    
    def reverse(self):
        """Winch reverse (down)"""
        GPIO.output(PIN_WINCH_RELAY_FORWARD, GPIO.LOW)
        time.sleep(0.05)  # Safety delay
        GPIO.output(PIN_WINCH_RELAY_REVERSE, GPIO.HIGH)
    
    def stop(self):
        """Stop winch"""
        GPIO.output(PIN_WINCH_RELAY_FORWARD, GPIO.LOW)
        GPIO.output(PIN_WINCH_RELAY_REVERSE, GPIO.LOW)
    
    def cleanup(self):
        self.stop()
        GPIO.cleanup()
