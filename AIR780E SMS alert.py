import serial
import time

def send_sms(phone_number, message):
    # Air780E usually uses /dev/ttyUSB2 for AT commands
    port = "/dev/ttyUSB2" 
    baud = 115200

    try:
        usb_serial = serial.Serial(port, baud, timeout=5)
        print(f"Connecting to {port}...")
        time.sleep(1)

        # 1. Set SMS to Text Mode
        usb_serial.write(b'AT+CMGF=1\r')
        time.sleep(1)
        
        # 2. Set the recipient number
        # Format: AT+CMGS="+1234567890"
        command = f'AT+CMGS="{phone_number}"\r'
        usb_serial.write(command.encode())
        time.sleep(1)

        # 3. Send the message body
        usb_serial.write(message.encode())
        time.sleep(1)

        # 4. Send Ctrl+Z (ASCII 26) to finish and send
        usb_serial.write(bytes([26]))
        time.sleep(2)

        # Read response
        response = usb_serial.read(usb_serial.in_waiting).decode()
        print("Response from Module:")
        print(response)

        if "OK" in response or "+CMGS:" in response:
            print("Successfully sent!")
        else:
            print("Failed to send. Check signal or SIM balance.")

        usb_serial.close()

    except Exception as e:
        print(f"Error: {e}")

# --- Usage ---
# Replace with your actual target number and message
dest_number = "+1234567890" 
text_body = "Hello from my Raspberry Pi 4 and Air780E!"

send_sms(dest_number, text_body)