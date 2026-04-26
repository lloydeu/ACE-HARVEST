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
        self._recv_buffer = ''
        self._recv_queue = []
    
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

        # Return any already-parsed messages first
        if self._recv_queue:
            return self._recv_queue.pop(0)

        try:
            data = self.sock.recv(4096).decode('utf-8')
            if data:
                self._recv_buffer += data
                lines = self._recv_buffer.split('\n')
                self._recv_buffer = lines.pop()  # Keep incomplete tail
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._recv_queue.append(json.loads(line))
                    except Exception:
                        pass

                if self._recv_queue:
                    return self._recv_queue.pop(0)
        except socket.timeout:
            return None
        except Exception:
            self.connected = False
        return None
    
    def close(self):
        if self.sock:
            self.sock.close()
