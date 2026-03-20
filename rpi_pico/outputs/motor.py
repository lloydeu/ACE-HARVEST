import machine

class Motor:
    def __init__(self, pin_forward, pin_reverse, frequency=1000):
        self.pwm_fwd = machine.PWM(machine.Pin(pin_forward))
        self.pwm_rev = machine.PWM(machine.Pin(pin_reverse))
        self.pwm_fwd.freq(frequency)
        self.pwm_rev.freq(frequency)
        self.stop()
    
    def set_raw(self, duty_fwd, duty_rev):
        self.pwm_fwd.duty_u16(duty_fwd)
        self.pwm_rev.duty_u16(duty_rev)
    
    def stop(self):
        self.set_raw(0, 0)
