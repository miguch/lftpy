from reliableUDP.connection import rUDPConnection
from reliableUDP.log import logger
from reliableUDP.utilities import *
import random


class clientConn:
    def __init__(self, addr, conn):
        self.addr = addr
        self.conn = conn
        self.state = SendStates.CLOSED

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState


class rUDPClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.conn = rUDPConnection(ip, port)

    def establishConn(self, destIP, destPort):
        #random seq in first handshake
        seqNum = random.randint(0, 2 ** 16)
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPoer: destPort,
            Sec.seqNum: seqNum,
            Sec.ackNum: 0,
            Sec.SYN: 1,

        })


    def send_msg(self):


