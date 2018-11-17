from reliableUDP.log import logger
import socket

class rUDPConnection:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((ip, port))
        logger.info("%s: Bind UDP on %s:%d" % (type(self).__name__, ip, port))


