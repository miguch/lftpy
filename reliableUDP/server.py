from reliableUDP.connection import rUDPConnection
from reliableUDP.utilities import RecvStates
from reliableUDP.log import logger


class rUDPServer(rUDPConnection):
    def __init__(self, ip, port):
        super(rUDPServer, self).__init__(ip, port)
        self.state = RecvStates.CLOSED

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def recv_msg(self):
        while True:
            data, addr = self.socket.recvfrom(2048)

    def process_recv_msg(self, data, addr):



