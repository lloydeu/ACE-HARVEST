import machine

""" PIN MAP """
# PIO State Machine
SM_ID_HX_710 = 0

# Sensors
PIN_HX710_SCK = 14
PIN_HX710_OUT = 15
PIN_ACS712_ADC_1 = 26 
PIN_ACS712_ADC_2 = 27
PIN_PH4502C_ADC = 28     

# Actuators (PWM)
SERVO_PINS = {
    "mg996_1": 18,
    "mg996_2": 19,
    "mg996_3": 20,
    "mg996_4": 21,
    "mg996_5": 22,
    "mg996_6": 2,
    "sg90": 3,
}  # {"servo_id": pin}

MOTOR_PINS = {
    "worm_gear_arm": [4, 5],
    "worm_gear_clamp": [6, 7],
    "linear_actuator": [8, 9],
    "vacuum_pump": [10, 11]
}  # {"motor_id": [f_pin, r_pin]}

# Actuators (Digital)
PIN_RELAY_LEFT_LIGHT = 12   # Relay 1 - Left Light
PIN_RELAY_RIGHT_LIGHT = 13  # Relay 2 - Right Light

""" CONSTANTS """
# Pressure (HX-710B)
PRESSURE_OFFSET = -234041
PRESSURE_SCALE = 0.000125

# pH Sensor (PH-4502C)
PH_STEP_VOLTAGE = 0.18  # Voltage change per pH unit (approx)
PH_7_VOLTAGE = 2.5      # Voltage at neutral pH 7

# Current (ACS712-20A with 5V logic → voltage divider → 3.3V ADC)
ACS_SENSITIVITY_1 = 0.100  # 20A module: 100mV/A
ACS_OFFSET_VOLTAGE_1 = 2.5
ACS_SENSITIVITY_2 = 0.100  # 20A module: 100mV/A
ACS_OFFSET_VOLTAGE_2 = 2.5

# FREQUENCY
MOTOR_FREQUENCY = 1000
SERVO_FREQUENCY = 50

# Safety Thresholds
STALL_THRESHOLD = 5.0      # Amps to trigger stall detection
STALL_DELAY_TICKS = 15     # 150ms buffer to ignore inrush current spikes

# Motor Safety Rules
# - Only ONE motor at a time (prevents power overload)
# - EXCEPTION: vacuum_pump can run simultaneously with any other motor
# - Stall detection only on motors with current sensors

# Motor-Specific Current Monitoring
# Map which current sensor monitors which motor
MOTOR_CURRENT_MAP = {
    "worm_gear_arm": "current_amps_1",      # Sensor 1 monitors arm
    "linear_actuator": "current_amps_2",    # Sensor 2 monitors actuator
    # "worm_gear_clamp": None,              # No stall detection
    # "vacuum_pump": None,                  # No stall detection
}

""" GLOBAL STATES """
state = {
    # Sensors
    "pressure_kpa": 0.0,
    "current_amps_1": 0.0,
    "current_amps_2": 0.0,
    "ph_level": 7.0,
    
    # Servos
    "servo_sg90_deg": 90,
    "servo_mg996_1_deg": 90,
    "servo_mg996_2_deg": 90,
    "servo_mg996_3_deg": 90,
    "servo_mg996_4_deg": 90,
    "servo_mg996_5_deg": 90,
    "servo_mg996_6_deg": 90,
    
    # Motors (-100 to 100)
    "motor_speeds": {motor_id: 0 for motor_id in MOTOR_PINS.keys()},
    
    # Relays
    "relay_left_light": False,
    "relay_right_light": False,
    
    # System
    "system_error": None,
    "is_calibrating": False
}