# motor.py

from machine import Pin, PWM

class Motor:
    def __init__(self, pin_1, pin_2, freq=10000):
        self.pwm1 = PWM(Pin(pin_1))
        self.pwm2 = PWM(Pin(pin_2))
        self.pwm1.freq(freq)
        self.pwm2.freq(freq)
        self.stop()

    def set_raw(self, duty1, duty2):
        """
        Directly sets the two PWM channels.
        duty1/duty2: 0 to 65535
        """
        self.pwm1.duty_u16(duty1)
        self.pwm2.duty_u16(duty2)

    def stop(self):
        """Soft brake (0, 0)"""
        self.set_raw(0, 0)