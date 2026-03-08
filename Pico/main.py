import config
from sensors import HX710B, ACS712, PH4502C
from outputs import Relay, Motor, Servo
from utils import MovingAverage
from usb_serial_bidirectional import USBBidirectional, usb_bidirectional_task

import utime, os, uasyncio as asyncio

# Input sensors
pressure_sensor = HX710B(config.SM_ID_HX_710, config.PIN_HX710_SCK, config.PIN_HX710_OUT)
pressure_filter = MovingAverage(10)
current_sensor_1 = ACS712(config.PIN_ACS712_ADC_1)
current_filter_1 = MovingAverage(50)
current_sensor_2 = ACS712(config.PIN_ACS712_ADC_2)
current_filter_2 = MovingAverage(50)
ph_sensor = PH4502C(config.PIN_PH4502C_ADC)
ph_filter = MovingAverage(10)

# Output devices
relay_1 = Relay(config.PIN_RELAY_1)
relay_2 = Relay(config.PIN_RELAY_2)

motors = {motor_id: Motor(pins[0], pins[1], config.MOTOR_FREQUENCY) for motor_id, pins in config.MOTOR_PINS.items()}
servos = {servo_id: Servo(pin, config.SERVO_FREQUENCY) for servo_id, pin in config.SERVO_PINS.items()}

# USB Bidirectional Communication with RPi4 Top
usb = USBBidirectional()

async def pressure_task():
    while True:     
        if pressure_sensor.data_available():
            raw = pressure_sensor.read_raw()
   
            kpa = (raw - config.PRESSURE_OFFSET) * config.PRESSURE_SCALE
            
            config.state["pressure_kpa"] = pressure_filter.update(kpa)
            
        await asyncio.sleep_ms(50)  # 20Hz Sampling
        
async def current_task():
    while True:
        raw_1 = current_sensor_1.read_raw()
        raw_2 = current_sensor_2.read_raw()
        
        voltage_1 = (raw_1 / 65535) * 3.3
        voltage_2 = (raw_2 / 65535) * 3.3
        
        amps_1 = (voltage_1 - config.ACS_OFFSET_VOLTAGE_1) / config.ACS_SENSITIVITY_1
        amps_2 = (voltage_2 - config.ACS_OFFSET_VOLTAGE_2) / config.ACS_SENSITIVITY_2
        
        config.state["current_amps_1"] = current_filter_1.update(amps_1)
        config.state["current_amps_2"] = current_filter_2.update(amps_2)
        
        await asyncio.sleep_ms(10)

async def ph_task():
    while True:
        raw = ph_sensor.read_raw()
        
        voltage = (raw / 65535) * 3.3
        
        ph_val = 7.0 + ((config.PH_7_VOLTAGE - voltage) / config.PH_STEP_VOLTAGE)
        
        config.state["ph_level"] = ph_filter.update(ph_val)
        
        await asyncio.sleep_ms(100)
        
async def relay_task():
    while True:
        relay_1.set_state(config.state["relay_1"])
        relay_2.set_state(config.state["relay_2"])
        
        await asyncio.sleep_ms(100)

async def motor_guard():
    """
    Motor safety guard with alerts sent to RPi4 Top
    """
    stall_timers = {motor_id: 0 for motor_id in motors.keys()}
    
    while True:
        # Get active motors
        requested = [motor_id for motor_id, speed in config.state["motor_speeds"].items() if speed != 0]

        # Rule 1: Only one motor at a time
        if len(requested) > 1:
            for motor_id in config.state["motor_speeds"]: 
                config.state["motor_speeds"][motor_id] = 0
            config.state["system_error"] = "CONFLICT"
            # Alert RPi4 Top about conflict
            usb.send_alert("CONFLICT", "Multiple motors requested simultaneously", "error")

        # Rule 2: Stall detection for the 2 specific motors
        active = requested[0] if len(requested) == 1 else None
        
        if active in ["linear_actuator", "worm_gear_arm"]:
            # Map Sensor 1 to Actuator, Sensor 2 to Arm
            current = config.state["current_amps_1"] if active == "linear_actuator" else config.state["current_amps_2"]
            
            if current > config.STALL_THRESHOLD:
                stall_timers[active] += 1
                if stall_timers[active] > config.STALL_DELAY_TICKS:
                    config.state["motor_speeds"][active] = 0
                    error_msg = f"STALL_{active.upper()}"
                    config.state["system_error"] = error_msg
                    # Alert RPi4 Top about stall
                    usb.send_alert("STALL", f"Motor stall detected: {active}", "critical")
            else:
                stall_timers[active] = 0
        
        await asyncio.sleep_ms(10)

async def motor_task(motors):
    last_speeds = {motor_id: 0 for motor_id in motors.keys()}

    while True:
        for motor_id, driver in motors.items():
            target_speed = config.state["motor_speeds"].get(motor_id, 0)

            if target_speed != last_speeds[motor_id]:
                duty = int((min(abs(target_speed), 100) / 100) * 65535)
                
                if target_speed > 0:
                    driver.set_raw(duty, 0)
                elif target_speed < 0:
                    driver.set_raw(0, duty)
                else:
                    driver.set_raw(0, 0)
        
                last_speeds[motor_id] = target_speed

        await asyncio.sleep_ms(20)
        
async def servo_task(servos):
    last_angles = {servo_id: -1 for servo_id in servos.keys()}
    
    while True:
        moved = False
        
        for servo_id, driver in servos.items():
            # Map servo_id to state key (e.g., "mg996_1" -> "servo_mg996_1_deg")
            state_key = f"servo_{servo_id}_deg"
            angle = config.state.get(state_key, 90)
            
            if angle != last_angles[servo_id]:
                # 1. Calculate Raw Duty (0-180 -> 1638-8192)
                duty = int(1638 + (angle / 180) * 6554)
                driver.set_raw(duty)
                
                # 2. Update memory
                last_angles[servo_id] = angle
                
                # 3. Dynamic Delay Logic
                # SG90 is fast (low delay); MG996 is heavy (long delay)
                if "sg90" in servo_id:
                    delay_ms = 150  # Fast snap
                else:
                    delay_ms = 400  # Heavy swing for MG996
                
                await asyncio.sleep_ms(delay_ms)
                
                moved = True
                break  # One servo at a time - exit loop after movement
        
        # Only sleep if no servo moved (prevents double-delay)
        if not moved:
            await asyncio.sleep_ms(50)
        
async def main():        
    await asyncio.gather(
        motor_guard(),
        pressure_task(),
        current_task(),
        ph_task(),
        relay_task(),
        motor_task(motors),
        servo_task(servos),
        usb_bidirectional_task(usb, config.state)  # Bidirectional communication with RPi4 Top
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        for driver in motors.values():
            driver.set_raw(0, 0)
        print("System Stopped.")
