from .connection import rUDPConnection, message
from .lftplog import logger
from .utilities import *
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
        self.messages = msgPool()

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
        fill_checksum(headerData, bytearray())
        logger.debug("First handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer((self.destIP, self.destPort))
        self.messages.add_msg(syn_msg, self.seqNum+1)
        self.update_state(SendStates.SYN_SENT)


    def third_handshake(self):
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
        fill_checksum(headerData, bytearray())
        logger.debug("Third handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer((self.destIP, self.destPort))
        self.messages.add_msg(syn_msg, self.seqNum+1)
        self.update_state(SendStates.ESTABLISHED)

    def handshake(self):
        logger.debug('Performing first handshake')
        self.establish_conn()
        logger.debug('Waiting for second handshake')
        data, addr = self.conn.socket.recvfrom(100)
        headerDict = header_to_dict(data)
        while not (addr == (self.destIP, self.destPort) and
                   check_header_checksum(data) and
                   self.check_establish_header(headerDict)):
            data, addr = self.conn.socket.recvfrom(100)
            headerDict = header_to_dict(data)
        self.messages.ack_msg(self.seqNum+1)
        self.serverSeq = headerDict[Sec.seqNum]
        self.third_handshake()


    def check_establish_header(self, headerDict: dict):
        if headerDict[Sec.dPort] != self.port or headerDict[Sec.sPort] != self.destPort:
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

    def finish_conn(self):
        logger.debug('Closing connection.')
        self.first_wavehand()
        self.second_third_wavehand()
        self.fourth_wavehand()



    def first_wavehand(self):
        logger.debug('Sending first wave header')
        self.seqNum = self.seqNum + 1
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq,
            Sec.ACK: 1,
            Sec.FIN: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("First wave sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer((self.destIP, self.destPort))
        self.messages.add_msg(syn_msg, self.seqNum+1)
        self.update_state(SendStates.FIN_WAIT_1)

    def check_second_wave(self, headerDict: dict):
        if headerDict[Sec.ackNum] != self.seqNum + 1:
            return False
        if headerDict[Sec.FIN] or not headerDict[Sec.ACK]:
            return False
        if headerDict[Sec.dPort] != self.port or headerDict[Sec.sPort] != self.destPort:
            return False
        return True

    def check_third_wave(self, headerDict: dict):
        if headerDict[Sec.ackNum] != self.seqNum + 1:
            return False
        if not headerDict[Sec.FIN] or not headerDict[Sec.ACK]:
            return False
        if headerDict[Sec.dPort] != self.port or headerDict[Sec.sPort] != self.destPort:
            return False
        return True

    def second_third_wavehand(self):
        logger.debug('Waiting for second wave')
        data, addr = self.conn.socket.recvfrom(100)
        headerDict = header_to_dict(data)
        second = False
        third = False
        while not (addr == (self.destIP, self.destPort) and
                   check_header_checksum(data) and
                   second and third):
            if self.check_second_wave(headerDict):
                second = True
                self.update_state(SendStates.FIN_WAIT_2)
                self.messages.ack_msg(self.seqNum+1)
            elif self.check_third_wave(headerDict):
                third = True
            data, addr = self.conn.socket.recvfrom(100)
            headerDict = header_to_dict(data)


    def close(self):
        self.conn.socket.close()
        self.update_state(SendStates.CLOSED)

    def fourth_wavehand(self):
        logger.debug('Sending first wave header')
        self.seqNum = self.seqNum + 1
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq,
            Sec.ACK: 1,
            Sec.FIN: 0
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("First wave sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send((self.destIP, self.destPort))
        self.update_state(SendStates.TIME_WAIT)
        threading.Timer(30, self.close)
