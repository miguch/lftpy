import socket
from .lftplog import logger

class rUDPConnection:
    def __init__(self, ip=None, port=None):
        self.ip = ip
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if ip is not None:
            self.socket.bind((ip, port))
            (self.ip, self.port) = self.socket.getsockname()
            logger.info("%s: Bind UDP on %s:%d" % (type(self).__name__, ip, port))
        else:
            logger.debug("%s: Created rUDPConnection object" % (type(self).__name__))


