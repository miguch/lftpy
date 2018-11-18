from reliableUDP.log import logger
import socket
import threading

class rUDPConnection:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((ip, port))
        logger.info("%s: Bind UDP on %s:%d" % (type(self).__name__, ip, port))


class message:
    def __init__(self, data, conn:rUDPConnection):
        self.acked = False
        self.data = data
        self.conn = conn
        # initial time out is 1000 ms
        self.timeoutTime = 1

    def send_with_timer(self, destAddr):
        if not self.acked:
            self.send(destAddr)
            t = threading.Timer(self.timeoutTime, self.send_with_timer, args=destAddr)
            t.start()

    def send(self, destAddr):
        self.conn.socket.sendto(self.data, self.addr)

