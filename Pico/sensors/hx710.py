# hx710.py

import rp2
from machine import Pin

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW, in_shiftdir=rp2.PIO.SHIFT_LEFT)
def hx710_program():
    wrap_target()
    wait(0, pin, 0)         
    set(x, 23)              
    label("bit_loop")
    set(pins, 1)    [1]      
    in_(pins, 1)            
    set(pins, 0)    [1]     
    jmp(x_dec, "bit_loop")   
    
    
    set(pins, 1)    [1]
    set(pins, 0)    [1]
    
    push(block)              
    wrap()

class HX710B:
    def __init__(self, sm_id, pin_sck, pin_out):
        """
        sm_id: PIO State Machine ID (0-7)
        pin_sck: Clock Pin (Output)
        pin_out: Data Pin (Input)
        """
        self.sm = rp2.StateMachine(
            sm_id, 
            hx710_program, 
            freq=1_000_000, 
            set_base=Pin(pin_sck), 
            in_base=Pin(pin_out)
        )
        self.sm.active(1)

    def data_available(self):
        """Returns True if there is a raw reading in the hardware mailbox."""
        return self.sm.rx_fifo() > 0

    def read_raw(self):
        """Pulls raw data and handles 24-bit sign extension."""
        raw = self.sm.get()
        # Convert 24-bit unsigned to signed integer
        if raw & 0x800000:
            raw -= 0x1000000
        return raw