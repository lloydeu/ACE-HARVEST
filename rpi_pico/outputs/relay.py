import machine

class Relay:
    def __init__(self, pin):
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.pin.value(0)
    
    def set_state(self, state):
        self.pin.value(1 if state else 0)
    
    def on(self):
        self.set_state(True)
    
    def off(self):
        self.set_state(False)
