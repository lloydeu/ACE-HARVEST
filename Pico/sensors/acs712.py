# acs712t.py

import machine

class ACS712:
    def __init__(self, pin_adc):
        """Initialize the ADC on the specified pin."""
        self.adc = machine.ADC(pin_adc)

    def read_raw(self):
        """Returns the raw 16-bit integer (0-65535)."""
        return self.adc.read_u16()