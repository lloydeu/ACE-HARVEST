# ph-4502c.py

import machine

class PH4502C:
    def __init__(self, pin_adc):
        """Initialize the ADC for the pH module."""
        self.adc = machine.ADC(pin_adc)

    def read_raw(self):
        """Returns the raw 16-bit integer."""
        return self.adc.read_u16()