"""Liquid Level Sensor Input"""
import RPi.GPIO as GPIO
from config import PIN_LIQUID_LEVEL

class LiquidSensorInput:
    """DFRobot liquid level sensor"""
    
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_LIQUID_LEVEL, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    def read(self):
        """Check if liquid detected (LOW = detected)"""
        return GPIO.input(PIN_LIQUID_LEVEL) == GPIO.LOW
