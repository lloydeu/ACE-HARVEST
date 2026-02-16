import os
import time
import RPi.GPIO as GPIO

def main():
    #do something
    print("Water Detected!")
    os.system('aplay /path/to/sound_alert.wav')


if __name__ == "__main__":
    main()