import threading
import socket
import select
import time
try:
    import paramiko
except ImportError:
    paramiko = None

class SSHTunnel:
    """
    Establish an SSH Tunnel for MySQL Connection.
    Forwards local port -> remote host:port via SSH.
    """
    def __init__(self, ssh_host, ssh_user, ssh_password, remote_bind_address=('127.0.0.1', 3306), local_bind_address=('127.0.0.1', 0), ssh_port=22):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.remote_bind_address = remote_bind_address 
        self.local_bind_address = local_bind_address
        self.server = None
        self.client = None
        self.local_port = None
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if not paramiko:
            raise ImportError("paramiko not installed")

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"SSH Connecting to {self.ssh_host}...")
        self.client.connect(
            self.ssh_host, 
            port=self.ssh_port, 
            username=self.ssh_user, 
            password=self.ssh_password,
            timeout=10
        )
        
        # Setup Forwarding
        class ThreadingTCPServer(socket.socket):
            pass

        # Find a free port if 0 is specified
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Retry logic for binding
        bind_success = False
        for i in range(5):
            try:
                sock.bind(self.local_bind_address)
                bind_success = True
                break
            except OSError:
                # If port 0 (random) fails, it's rare. If fixed port, wait.
                # Assuming local_bind_address is dynamic (ip, 0) usually.
                time.sleep(0.5)
        
        if not bind_success:
             raise OSError(f"Could not bind to local address {self.local_bind_address} after retries")

        self.local_port = sock.getsockname()[1]
        sock.listen(1)
        
        self.local_bind_address = ('127.0.0.1', self.local_port)
        
        print(f"Tunnel Listening on {self.local_bind_address} -> forwarding to {self.remote_bind_address}")
        
        self._thread = threading.Thread(target=self._forward_loop, args=(sock,))
        self._thread.daemon = True
        self._thread.start()
        
        return self.local_port

    def _forward_loop(self, sock):
        while not self._stop_event.is_set():
            r, _, _ = select.select([sock], [], [], 1.0)
            if sock in r:
                client_sock, addr = sock.accept()
                self._handle_forward(client_sock)

    def _handle_forward(self, local_sock):
        try:
            remote_sock = self.client.get_transport().open_channel(
                'direct-tcpip', 
                self.remote_bind_address, 
                local_sock.getpeername()
            )
            if remote_sock is None:
                local_sock.close()
                return

            self._bridge_sockets(local_sock, remote_sock)
        except Exception as e:
            print(f"Tunnel Forward Error: {e}")
            local_sock.close()

    def _bridge_sockets(self, s1, s2):
        # Determine strict direction? No, bi-directional
        # Simple loop
        chan1 = s1
        chan2 = s2
        
        def forward(source, dest):
            while not self._stop_event.is_set():
                try:
                    data = source.recv(4096)
                    if len(data) == 0: break
                    dest.send(data)
                except:
                    break
            try: 
                source.close() 
            except: pass
            try: 
                dest.close() 
            except: pass

        t1 = threading.Thread(target=forward, args=(chan1, chan2))
        t2 = threading.Thread(target=forward, args=(chan2, chan1))
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

    def stop(self):
        self._stop_event.set()
        if self.client:
            self.client.close()
        print("SSH Tunnel Stopped.")

