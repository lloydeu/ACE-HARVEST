import machine

class Servo:
    def __init__(self, pin, frequency=50):
        self.pwm = machine.PWM(machine.Pin(pin))
        self.pwm.freq(frequency)
        self.set_angle(90)
    
    def set_raw(self, duty):
        self.pwm.duty_u16(duty)
    
    def set_angle(self, angle):
        angle = max(0, min(180, angle))
        duty = int(1638 + (angle / 180) * 6554)
        self.set_raw(duty)
