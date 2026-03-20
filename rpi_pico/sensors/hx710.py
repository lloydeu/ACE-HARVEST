import machine
import rp2

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW, out_init=rp2.PIO.OUT_LOW, fifo_join=rp2.PIO.JOIN_RX)
def hx710_read():
    wrap_target()
    # Wait for the sensor to pull the data pin low (Ready)
    wait(0, pin, 0)
    
    # Shift in 24 bits
    set(x, 23)
    label("bitloop")
    set(pins, 1) [1]   # SCK High
    in_(pins, 1)       # Sample Data
    set(pins, 0) [1]   # SCK Low
    jmp(x_dec, "bitloop")
    
    # 25th pulse for HX710B
    set(pins, 1) [1]
    set(pins, 0) [1]
    
    # Push the full word to the RX FIFO
    push(noblock) 
    wrap()

class HX710B:
    def __init__(self, sm_id, sck_pin, data_pin):
        self.sck = machine.Pin(sck_pin, machine.Pin.OUT)
        # Added internal pull-up to prevent floating pin noise when disconnected
        self.data = machine.Pin(data_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        
        self.sm = rp2.StateMachine(
            sm_id, 
            hx710_read, 
            freq=1_000_000, 
            set_base=self.sck, 
            in_base=self.data
        )
        self.sm.active(1)
    
    def data_available(self):
        # Checks the State Machine FIFO instead of the raw Pin.
        # This returns True ONLY when a full 24-bit reading is ready.
        return self.sm.rx_fifo() > 0
    
    def read_raw(self):
        # If called when no data is ready, it returns 0 immediately instead of hanging.
        if self.sm.rx_fifo() == 0:
            return 0
            
        raw = self.sm.get()
        
        # Handle 24-bit two's complement
        if raw & 0x800000:
            raw -= 0x1000000
        return raw