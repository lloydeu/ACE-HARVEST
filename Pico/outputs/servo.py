# servo.py

from machine import Pin, PWM

class Servo:
    def __init__(self, pin_id, freq = 50):
        """Initializes a PWM pin at the standard 50Hz for servos."""
        self.pwm = PWM(Pin(pin_id))
        self.pwm.freq(freq) 
       
        self.pwm.duty_u16(0)

    def set_raw(self, duty):
        """
        The Raw Manifest: Directly sets the 16-bit duty cycle.
        Expected range for 50Hz servos: ~1638 (0.5ms) to ~8192 (2.5ms).
        """
        # Constrain to 16-bit range to prevent crashes
        duty = max(0, min(65535, int(duty)))
        self.pwm.duty_u16(duty)