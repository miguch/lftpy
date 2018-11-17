import threading

from reliableUDP.connection import rUDPConnection
from reliableUDP.utilities import RecvStates
from reliableUDP.log import logger

class serverConn:
    def __init__(self, addr, conn):
        self.addr = addr
        self.conn = conn
        self.state = RecvStates.CLOSED

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState


class rUDPServer:
    def __init__(self, ip, port):
        self.conn = rUDPConnection(ip, port)
        self.connections = {}


    def recv_msg(self):
        while True:
            data, addr = self.socket.recvfrom(2048)
            threading.Thread(target=self.process_recv_msg, args=(data, addr))

    def process_recv_msg(self, data, addr):



