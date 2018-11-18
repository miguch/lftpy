from reliableUDP.connection import *
from reliableUDP.log import logger
from reliableUDP.utilities import *
import random


class rUDPClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.conn = rUDPConnection(ip, port)
        self.state = SendStates.CLOSED
        self.destIP = ""
        self.destPort = 0
        self.seqNum = 0
        self.serverSeq = 0

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def establish_conn(self):
        # random seq in first handshake
        self.seqNum = random.randint(0, 2 ** 16)
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: 0,
            Sec.ACK: 0,
            Sec.SYN: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray(), ip_to_bytes(self.ip), ip_to_bytes(self.destIP))
        logger.debug("First handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer((self.destIP, self.destPort))
        self.update_state(SendStates.SYN_SENT)


    def second_handshake(self):
        self.seqNum = self.seqNum + 1
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq + 1,
            Sec.ACK: 1,
            Sec.SYN: 0
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray(), ip_to_bytes(self.ip), ip_to_bytes(self.destIP))
        logger.debug("Second handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer((self.destIP, self.destPort))
        self.update_state(SendStates.SYN_SENT)

    def handshake(self):
        logger.debug('Performing first handshake')
        self.establish_conn()
        logger.debug('Waiting for second handshake')
        data, addr = self.conn.socket.recvfrom(100)
        headerDict = header_to_dict(data)
        while not (addr == (self.destIP, self.destPort) and
                   check_header_checksum(data, ip_to_bytes(self.ip), ip_to_bytes(self.destIP)) and
                   self.check_establish_header(headerDict)):
            data, addr = self.conn.socket.recvfrom(100)
        self.serverSeq = headerDict[Sec.seqNum]
        self.second_handshake()


    def check_establish_header(self, headerDict: dict):
        if headerDict.dPort != self.port or headerDict.sPort != self.destPort:
            return False
        if not (headerDict[Sec.SYN] and headerDict[Sec.ACK]):
            return False
        return headerDict[Sec.ackNum] == self.seqNum + 1

    def connect(self, destIP, destPort):
        if self.state == SendStates.CLOSED:
            logger.info('Establishing connection to %s:%d' % (destIP, destPort))
            self.destIP = destIP
            self.destPort = destPort
            self.handshake()

    def send_msg(self, data):
        if self.state == SendStates.CLOSED:
            logger.error("Sending message without establishing connection.")
            raise Exception("Connection not established.")
