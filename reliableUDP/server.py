import threading

from reliableUDP.connection import *
from reliableUDP.utilities import *
from reliableUDP.log import logger
import random

class serverConn:
    def __init__(self, addr, conn):
        # addr is the target address
        self.addr = addr
        self.conn = conn
        self.state = RecvStates.LISTEN
        self.seqNum = 0
        self.clientSeq = 0
        self.messages = {}
        logger.debug('Create a server connection to %s' % str(addr))

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def handshake(self):
        # random seq
        self.seqNum = random.randint(0, 2 ** 16)
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq+1,
            Sec.SYN: 1,
            Sec.ACK: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray(), ip_to_bytes(self.ip), ip_to_bytes(self.destIP))
        logger.debug("Server Second handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer(self.addr)
        self.update_state(RecvStates.SYN_RCVD)
        self.seqNum += 1
        self.clientSeq += 1

    def processData(self, data):
        headerDict = header_to_dict(data)
        if headerDict[Sec.ACK]:
            self.processACK(headerDict)


    def processACK(self, headerDict):
        ackNum = headerDict[Sec.ackNum]
        if ackNum in self.messages:
            self.messages[ackNum].acked = True
            self.messages.pop(ackNum)


class rUDPServer:
    def __init__(self, ip, port):
        self.conn = rUDPConnection(ip, port)
        # The server will identify each connection with
        # a tuple of clients' address and port
        self.connections = {}


    def recv_msg(self):
        while True:
            data, addr = self.conn.socket.recvfrom(2048)
            threading.Thread(target=self.process_recv_msg, args=(data, addr))

    def process_recv_msg(self, data, addr):
        headerDict = header_to_dict(data)
        if headerDict[Sec.SYN] and not headerDict[Sec.ACK]:
            # First handshake
            self.conn[addr] = serverConn(addr, self.conn)
            self.conn[addr].clientSeq = headerDict[Sec.seqNum]





