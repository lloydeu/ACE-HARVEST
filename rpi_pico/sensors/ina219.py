from machine import Pin, I2C, ADC
from ina219 import INA219
import utime

class BatteryMonitor:

    def __init__(self):
        self.adc = ADC(27)   # replaced old ACS712 #2 ADC pin

        self.i2c = I2C(
            1,
            scl=Pin(17),
            sda=Pin(16),
            freq=400000
        )

        self.ina = INA219(0.000375, self.i2c)
        self.ina.configure()

        self.used_ah = 0
        self.last_time = utime.time()

    def voltage(self):
        raw = self.adc.read_u16()
        return (raw / 65535) * 3.3 * 4.7

    def current(self):
        try:
            return self.ina.current() / 1000
        except:
            return 0

    def update(self):
        now = utime.time()
        dt = now - self.last_time
        self.last_time = now

        amps = self.current()

        if amps > 0:
            self.used_ah += amps * dt / 3600

    def percent(self):
        soc = 100 - self.used_ah

        if soc > 100:
            soc = 100
        if soc < 0:
            soc = 0

        return soc