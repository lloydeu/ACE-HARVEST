import time
import os

import RPi.GPIO as GPIO

class WaterLevelSensor:
    def __init__(self, channel):
        self.channel = channel
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.channel, GPIO.IN)
    
    def read_level(self):
        # Read the digital value from the sensor
        return GPIO.input(self.channel)
    
    def cleanup(self):
        GPIO.cleanup()

def main():
    # Initialize sensor on GPIO pin
    SENSOR_PIN = 17
    sensor = WaterLevelSensor(SENSOR_PIN)
    
    try:
        while True:
            level = sensor.read_level()
            if level == 1:
                print("Water Detected!")
                # Play sound alert
                os.system('aplay /path/to/sound_alert.wav')
            else:
                print("No Water Detected")
            time.sleep(1)  # Read every second
            
    except KeyboardInterrupt:
        print("\nProgram stopped by user")
        sensor.cleanup()

if __name__ == "__main__":
    main()