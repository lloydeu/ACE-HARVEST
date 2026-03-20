"""RPi Top TCP Client"""
import socket
import json

class TopClient:
    """TCP client for RPi Top"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False
    
    def connect(self):
        """Connect to RPi Top"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(1.0)
            self.connected = True
            print('connecting')
            return True
        except ConnectionError as c:
            print(c)
            self.connected = False

            return False
    
    def send_command(self, command):
        """Send command to RPi Top"""
        if not self.connected:
            return False
        try:
            msg = json.dumps(command)
            self.sock.sendall(f"{msg}\n".encode('utf-8'))
            return True
        except:
            self.connected = False
            return False
    
    def receive(self):
        """Receive data from RPi Top"""
        if not self.connected:
            return None
        try:
            data = self.sock.recv(4096).decode('utf-8').strip()
            if data:
                return json.loads(data)
        except socket.timeout:
            return None
        except:
            self.connected = False
        return None
    
    def close(self):
        if self.sock:
            self.sock.close()
