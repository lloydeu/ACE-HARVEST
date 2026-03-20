import machine

""" 
FINAL HARDWARE CONFIGURATION
Based on actual wiring diagram and component list

Power Supply:
- 12V Supply → XL-4015 5V 5A → Pico
- 12V Supply → HCW-P715 5V 6A x 2 → RPi Pico (redundant/backup)
- 12V Supply → Motor Drivers
- 12V Supply → Solenoid Valve (via relay)
"""

# ==================== PIO STATE MACHINE ====================
SM_ID_HX_710 = 0

# ==================== SENSORS (Connected to Pico) ====================
# Pressure Sensor (HX710B)
PIN_HX710_SCK = 14
PIN_HX710_OUT = 15

# Current Sensors (ACS712) - for stall detection
PIN_ACS712_ADC_1 = 26  # Monitors Motor Driver 1 (worm gears)
PIN_ACS712_ADC_2 = 27  # Monitors Motor Driver 2 (linear actuator)

# pH Level Sensor
PIN_PH_4502C_ADC = 28

# ==================== SERVOS (Connected to Pico) ====================
SERVO_PINS = {
    # SG90 - Fast, lightweight servo
    "sg90": 3,
    
    # MG996 x 6 - Heavy duty servos
    "mg996_1": 18,
    "mg996_2": 19,
    "mg996_3": 20,
    "mg996_4": 21,
    "mg996_5": 22,
    "mg996_6": 2,
}

# ==================== MOTOR DRIVER 1 (Connected to Pico) ====================
# Controls: Worm Gear Motor Arm, Worm Gear Motor Clamp
# Current monitored by ACS712 Sensor 1 (GPIO 26)
MOTOR_DRIVER_1_PINS = {
    "worm_gear_arm": [4, 5],
    "worm_gear_clamp": [6, 7],
}

MOTOR_DRIVER_2_PINS = {
    "linear_actuator": [8, 9],
    "vacuum_pump": [10, 11],
}

# Create an empty dict and update it with the contents of the others
MOTOR_PINS = {}
MOTOR_PINS.update(MOTOR_DRIVER_1_PINS)
MOTOR_PINS.update(MOTOR_DRIVER_2_PINS)
# ==================== 2 CHANNEL RELAY (Connected to Pico) ====================
# Relay 1: Lights
# Relay 2: Solenoid Valve
PIN_RELAY_LIGHTS = 12        # Relay Channel 1 → Lighting System
PIN_RELAY_VALVE = 13      # Relay Channel 2 → Solenoid Valve

# ==================== SENSOR CONSTANTS ====================
# Pressure Sensor (HX710B)
PRESSURE_OFFSET = -234041
PRESSURE_SCALE = 0.000125

# pH Sensor
PH_STEP_VOLTAGE = 0.18  # Voltage change per pH unit (approx)
PH_7_VOLTAGE = 2.5      # Voltage at neutral pH 7

# Current Sensors (ACS712-20A with voltage divider for 3.3V ADC)
ACS_SENSITIVITY_1 = 0.100  # 20A module: 100mV/A
ACS_OFFSET_VOLTAGE_1 = 2.5
ACS_SENSITIVITY_2 = 0.100  # 20A module: 100mV/A
ACS_OFFSET_VOLTAGE_2 = 2.5

# ==================== PWM FREQUENCIES ====================
MOTOR_FREQUENCY = 1000  # 1 kHz for motor PWM
SERVO_FREQUENCY = 50    # 50 Hz standard for servos

# ==================== SAFETY THRESHOLDS ====================
STALL_THRESHOLD = 5.0      # Amps to trigger stall detection
STALL_DELAY_TICKS = 15     # 150ms buffer to ignore inrush current spikes

# ==================== MOTOR CURRENT MONITORING ====================
# Map which current sensor monitors which motor
MOTOR_CURRENT_MAP = {
    # Motor Driver 1 - monitored by Current Sensor 1
    "worm_gear_arm": "current_amps_1",
    "worm_gear_clamp": "current_amps_1",
    
    # Motor Driver 2 - monitored by Current Sensor 2
    "linear_actuator": "current_amps_2",
    # "vacuum_pump": None,  # No stall detection (low current)
}

# ==================== MOTOR SAFETY RULES ====================
# - Only ONE motor at a time (prevents power overload)
# - EXCEPTION: vacuum_pump can run simultaneously with any other motor
#   (vacuum pump has low current draw and needs continuous operation)
# - Stall detection on: worm_gear_arm, worm_gear_clamp, linear_actuator
EXEMPT_MOTORS = ["vacuum_pump"]  # These can run with other motors

# ==================== GLOBAL STATE ====================
state = {
    # Sensors
    "pressure_kpa": 0.0,
    "current_amps_1": 0.0,  # Motor Driver 1 current
    "current_amps_2": 0.0,  # Motor Driver 2 current
    "ph_level": 7.0,
    
    # Servos (angles 0-180)
    "servo_sg90_deg": 90,
    "servo_mg996_1_deg": 90,
    "servo_mg996_2_deg": 90,
    "servo_mg996_3_deg": 90,
    "servo_mg996_4_deg": 90,
    "servo_mg996_5_deg": 90,
    "servo_mg996_6_deg": 90,
    
    # Motors (speed -100 to 100)
    "motor_speeds": {motor_id: 0 for motor_id in MOTOR_PINS.keys()},
    
    # Relays (True = energized/ON)
    "relay_lights": False,
    "relay_valve": False,  # Solenoid valve control
    
    # System status
    "system_error": None,
    "is_calibrating": False,
    "calibration_type": None,
    "calibration_result": None
}

# ==================== HARDWARE NOTES ====================
"""
MOTOR DRIVER 1 (Current Sensor 1):
- Worm Gear Motor Arm    → Stall detection ENABLED
- Worm Gear Motor Clamp  → Stall detection ENABLED
- Current sensor monitors total current for this driver

MOTOR DRIVER 2 (Current Sensor 2):
- Linear Actuator → Stall detection ENABLED
- Vacuum Pump     → Stall detection DISABLED (exempt from conflict rule)
- Current sensor monitors total current for this driver

RELAY MODULE:
- Channel 1: Lights (12V lighting system)
- Channel 2: Solenoid Valve (12V valve, normally closed)

STALL DETECTION:
- If Motor Driver 1 current > 5A for 150ms → stop both worm gear motors
- If Motor Driver 2 current > 5A for 150ms → stop linear actuator only
  (vacuum pump exempt)

CONFLICT PREVENTION:
- Only ONE motor active at a time (except vacuum_pump)
- Prevents power supply overload
- Example: Can run vacuum_pump + worm_gear_arm simultaneously
- Example: Cannot run worm_gear_arm + linear_actuator simultaneously
"""
