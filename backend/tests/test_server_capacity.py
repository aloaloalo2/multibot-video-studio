"""A burst of local browser requests must fit in the listen queue."""
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class ServerCapacity(unittest.TestCase):
    def test_accepts_a_burst_before_request_workers_start(self):
        server=app.StudioHTTPServer(('127.0.0.1',0),app.Handler)
        clients=[]
        try:
            for _ in range(32):
                clients.append(socket.create_connection(server.server_address,timeout=1))
            self.assertEqual(len(clients),32)
        finally:
            for client in clients:client.close()
            server.server_close()
