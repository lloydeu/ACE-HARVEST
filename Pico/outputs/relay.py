# relay.py

from machine import Pin

class Relay:
    def __init__(self, pin_id):
        """Initialize the relay pin as an output."""
        self.pin = Pin(pin_id, Pin.OUT)
        # Default to OFF (False)
        self.pin.value(0)

    def set_state(self, is_on):
        """
        Sets the relay state.
        is_on: Boolean or Integer (0 or 1)
        """
        if is_on:
            self.pin.value(0)
        else:
            self.pin.value(1)