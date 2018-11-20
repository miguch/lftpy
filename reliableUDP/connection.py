import socket
import threading
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


class message:
    def __init__(self, data, conn: rUDPConnection):
        self.acked = False
        self.data = data
        self.conn = conn
        # initial time out is 1000 ms
        self.timeoutTime = 1

    def send_with_timer(self, destAddr):
        if self.timeoutTime > 8:
            logger.warning('Timeout exceeds 3 times, reset timeout time')
            self.timeoutTime = 1
        if not self.acked:
            self.send(destAddr)
            t = threading.Timer(self.timeoutTime, self.send_with_timer, args=[destAddr])
            self.timeoutTime *= 2
            t.start()

    def send(self, destAddr):
        self.conn.socket.sendto(self.data, destAddr)

