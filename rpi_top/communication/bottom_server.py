"""TCP Server for RPi Bottom Communication"""
import socket
import json
import threading

class BottomServer:
    """TCP server to receive commands from Bottom and send telemetry"""
    
    def __init__(self, port):
        self.port = port
        self.sock = None
        self.client_sock = None
        self.running = False
        self.listen_thread = None
    
    def start(self):
        """Start TCP server"""
        if self.running:
            self.stop()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 0)
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.listen(1)
            self.sock.settimeout(1.0)

            self.running = True
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

            return True
        except Exception as e:
            print(f"Server start failed: {e}")
            self.running = False
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            return False
    
    def _listen_loop(self):
        """Accept client connections"""
        while self.running:
            try:
                client, addr = self.sock.accept()
                print(f"✓ Bottom connected from {addr}")
                self.client_sock = client
                self.client_sock.settimeout(1.0)
            except socket.timeout:
                continue
            except OSError as e:
                if not self.running:
                    break
                print(f"Accept error: {e}")
                break
            except Exception as e:
                print(f"Accept error: {e}")
                break
    
    def receive(self):
        """Receive command from Bottom"""
        if not self.client_sock:
            return None
        try:
            data = self.client_sock.recv(4096).decode('utf-8').strip()
            if data:
                return json.loads(data)
        except socket.timeout:
            return None
        except Exception:
            self.client_sock.close()
            self.client_sock = None
        return None
    
    def send_telemetry(self, data):
        """Send telemetry to Bottom"""
        if not self.client_sock:
            return False
        try:
            msg = json.dumps(data)
            self.client_sock.sendall(f"{msg}\n".encode('utf-8'))
            return True
        except Exception:
            self.client_sock.close()
            self.client_sock = None
            return False
    
    def send_alert(self, alert):
        """Send alert to Bottom"""
        return self.send_telemetry(alert)
    
    def stop(self):
        """Stop server"""
        self.running = False

        if self.client_sock:
            try:
                self.client_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.client_sock.close()
            except Exception:
                pass
            self.client_sock = None

        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

        if self.listen_thread:
            self.listen_thread.join(timeout=1.0)
            self.listen_thread = None
