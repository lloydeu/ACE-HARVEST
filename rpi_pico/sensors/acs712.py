import machine

class ACS712:
    def __init__(self, adc_pin):
        self.adc = machine.ADC(adc_pin)
    
    def read_raw(self):
        return self.adc.read_u16()
    
    def read_voltage(self):
        return (self.read_raw() / 65535) * 3.3
