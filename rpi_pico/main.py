import config
from machine import Pin
from sensors import HX710B, ACS712, PH4502C
from outputs import Relay, Motor, Servo
from utils import MovingAverage
from communication import USBBidirectional, usb_bidirectional_task

import utime, os, uasyncio as asyncio

# Input sensors
pressure_sensor = HX710B(config.SM_ID_HX_710, config.PIN_HX710_SCK, config.PIN_HX710_OUT)
pressure_filter = MovingAverage(10)
current_sensor_1 = ACS712(config.PIN_ACS712_ADC_1)
current_filter_1 = MovingAverage(50)
current_sensor_2 = ACS712(config.PIN_ACS712_ADC_2)
current_filter_2 = MovingAverage(50)
ph_sensor = PH4502C(config.PIN_PH_4502C_ADC)
ph_filter = MovingAverage(10)

# Output devices
relay_lights = Relay(config.PIN_RELAY_LIGHTS)
relay_valve = Relay(config.PIN_RELAY_VALVE)

motors = {motor_id: Motor(pins[0], pins[1], config.MOTOR_FREQUENCY) for motor_id, pins in config.MOTOR_PINS.items()}
servos = {servo_id: Servo(pin, config.SERVO_FREQUENCY) for servo_id, pin in config.SERVO_PINS.items()}

# USB Bidirectional Communication with RPi4 Top
usb = USBBidirectional()

# Pico LED for Crash Diagnostic
led = Pin("LED", Pin.OUT)

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
        relay_lights.set_state(config.state["relay_lights"])
        relay_valve.set_state(config.state["relay_valve"])
        
        await asyncio.sleep_ms(100)

async def motor_guard():
    """
    Motor safety guard with alerts sent to RPi4 Top
    
    Rules:
    1. Only one motor at a time (EXCEPT vacuum_pump can run with others)
    2. Stall detection for worm_gear_arm and linear_actuator
    """
    stall_timers = {motor_id: 0 for motor_id in motors.keys()}
    
    while True:
        # Get active motors (excluding vacuum_pump from conflict check)
        all_active = [motor_id for motor_id, speed in config.state["motor_speeds"].items() if speed != 0]
        requested = [motor_id for motor_id in all_active if motor_id != "vacuum_pump"]

        # Rule 1: Only one motor at a time (vacuum_pump exempt)
        if len(requested) > 1:
            # Stop the conflicting motors (but keep vacuum_pump running)
            for motor_id in requested: 
                config.state["motor_speeds"][motor_id] = 0
            config.state["system_error"] = "CONFLICT"
            # Alert RPi4 Top about conflict
            usb.send_alert("CONFLICT", "Multiple motors requested simultaneously", "error")

        # Rule 2: Stall detection for monitored motors
        active = requested[0] if len(requested) == 1 else None
        
        if active and active in config.MOTOR_CURRENT_MAP:
            # Get the current sensor reading for this motor
            sensor_name = config.MOTOR_CURRENT_MAP[active]
            current = config.state[sensor_name]
            
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
        
async def calibration_task():
    """
    Handles calibration requests from RPi4 Top
    - Pressure tare (zero)
    - pH calibration
    - Current offset calibration
    """
    while True:
        if config.state["is_calibrating"]:
            calib_type = config.state.get("calibration_type", "")
            
            if calib_type == "pressure_tare":
                # Take 50 samples over 2.5 seconds
                samples = []
                for _ in range(50):
                    if pressure_sensor.data_available():
                        raw = pressure_sensor.read_raw()
                        samples.append(raw)
                    await asyncio.sleep_ms(50)
                
                if samples:
                    avg_raw = sum(samples) / len(samples)
                    # Update offset so current reading becomes zero
                    config.PRESSURE_OFFSET = avg_raw
                    config.state["calibration_result"] = f"Tare complete: offset={avg_raw:.0f}"
                    
                    # Clear filter to restart with new zero
                    pressure_filter.clear()
                else:
                    config.state["calibration_result"] = "Tare failed: no data"
                
                config.state["is_calibrating"] = False
            
            elif calib_type == "ph_7_calibration":
                # Calibrate pH to 7.0 (neutral buffer)
                samples = []
                for _ in range(50):
                    raw = ph_sensor.read_raw()
                    voltage = (raw / 65535) * 3.3
                    samples.append(voltage)
                    await asyncio.sleep_ms(100)
                
                if samples:
                    avg_voltage = sum(samples) / len(samples)
                    # Update neutral voltage
                    config.PH_7_VOLTAGE = avg_voltage
                    config.state["calibration_result"] = f"pH 7 calibration complete: V={avg_voltage:.3f}"
                    
                    # Clear filter
                    ph_filter.clear()
                else:
                    config.state["calibration_result"] = "pH calibration failed"
                
                config.state["is_calibrating"] = False
            
            elif calib_type == "current_zero":
                # Zero current sensors (all motors must be OFF)
                samples_1 = []
                samples_2 = []
                
                for _ in range(100):
                    raw_1 = current_sensor_1.read_raw()
                    raw_2 = current_sensor_2.read_raw()
                    
                    voltage_1 = (raw_1 / 65535) * 3.3
                    voltage_2 = (raw_2 / 65535) * 3.3
                    
                    samples_1.append(voltage_1)
                    samples_2.append(voltage_2)
                    
                    await asyncio.sleep_ms(10)
                
                if samples_1 and samples_2:
                    avg_v1 = sum(samples_1) / len(samples_1)
                    avg_v2 = sum(samples_2) / len(samples_2)
                    
                    # Update offsets
                    config.ACS_OFFSET_VOLTAGE_1 = avg_v1
                    config.ACS_OFFSET_VOLTAGE_2 = avg_v2
                    
                    config.state["calibration_result"] = f"Current zero: V1={avg_v1:.3f}, V2={avg_v2:.3f}"
                    
                    # Clear filters
                    current_filter_1.clear()
                    current_filter_2.clear()
                else:
                    config.state["calibration_result"] = "Current zero failed"
                
                config.state["is_calibrating"] = False
        
        await asyncio.sleep_ms(100)
        
async def heartbeat():
    while True:
        led.toggle()
        await asyncio.sleep_ms(1000)

async def main():        
    await asyncio.gather(
        usb_bidirectional_task(usb, config.state), # connect to Rpi Top
        heartbeat(), # detect crashes
        motor_guard(), # one motor at a time to prevent overcurrent
        pressure_task(), # measure pressure
        current_task(), # measure current
        ph_task(), # measure pH
        relay_task(), # set relays based on state variables 
        motor_task(motors), # set motors based on state variables
        servo_task(servos), # set servos one at a time
        calibration_task() # handles calibration when requested by Rpi Top
       
       
    )
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        for driver in motors.values():
            driver.set_raw(0, 0)
        print("System Stopped.")