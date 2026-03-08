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
    "linear_actuator": [4, 5],
    "worm_gear_arm": [6, 7],
    "worm_gear_clamp": [8, 9],
    "worm_gear_cup": [10, 11]
}  # {"motor_id": [f_pin, r_pin]}

# Actuators (Digital)
PIN_RELAY_1 = 12
PIN_RELAY_2 = 13

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

""" GLOBAL STATES """
state = {
    "pressure_kpa": 0.0,
    "current_amps_1": 0.0,
    "current_amps_2": 0.0,
    "ph_level": 7.0,
    "servo_sg90_deg": 90,
    "servo_mg996_1_deg": 90,
    "servo_mg996_2_deg": 90,
    "servo_mg996_3_deg": 90,
    "servo_mg996_4_deg": 90,
    "servo_mg996_5_deg": 90,
    "servo_mg996_6_deg": 90,
    "motor_speeds": {motor_id: 0 for motor_id in MOTOR_PINS.keys()},  # -100 to 100
    "relay_1": False,
    "relay_2": False,
    "system_error": None,
    "is_calibrating": False
}