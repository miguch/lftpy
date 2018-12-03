from enum import Enum
import threading
from .connection import rUDPConnection
from .lftplog import logger

# noinspection PyArgumentList
RecvStates = Enum('RecvStates', ('CLOSED', 'LISTEN', 'SYN_REVD',
                                 'ESTABLISHED', 'CLOSE_WAIT', 'LAST_ACK'))

# noinspection PyArgumentList
SendStates = Enum('SendStates', ('CLOSED', 'SYN_SENT', 'ESTABLISHED',
                                 'FIN_WAIT_1', 'FIN_WAIT_2', 'TIME_WAIT'))

CwndState = Enum('CwndState', ('SLOWSTART', 'CONGAVOID', 'SHAKING'))

# The sections in TCP header
# noinspection PyArgumentList
Sec = Enum('headerStruct', ('sPort', 'dPort', 'seqNum', 'ackNum',
                                       'offset', 'NS', 'CWR', 'ECE', 'URG',
                                       'ACK', 'PSH', 'RST', 'SYN', 'FIN',
                                       'recvWin', 'checksum', 'urgPtr'))


# Custom header needs to define sPort, dPort, seqNum and ackNum
defaultHeaderDict = {
    Sec.offset: 5,
    Sec.NS: False,
    Sec.CWR: False,
    Sec.ECE: False,
    Sec.URG: False,
    Sec.ACK: False,
    Sec.PSH: False,
    Sec.RST: False,
    Sec.SYN: False,
    Sec.FIN: False,
    Sec.recvWin: 0,
    Sec.urgPtr: 0,
    Sec.checksum: 0
}

# The default header length is 20 bytes
defaultHeaderLen = 20


def header_to_dict(headerData: bytearray):
    result = dict()
    result[Sec.sPort] = int.from_bytes(headerData[0:2], byteorder='big', signed=False)
    result[Sec.dPort] = int.from_bytes(headerData[2:4], byteorder='big', signed=False)
    result[Sec.seqNum] = int.from_bytes(headerData[4:8], byteorder='big', signed=False)
    result[Sec.ackNum] = int.from_bytes(headerData[8:12], byteorder='big', signed=False)
    result[Sec.offset] = int.from_bytes([headerData[12] & 0xf0], byteorder='big', signed=False)
    result[Sec.NS] = bool(headerData[12] & 0x01)
    result[Sec.CWR] = bool(headerData[13] & 0x80)
    result[Sec.ECE] = bool(headerData[13] & 0x40)
    result[Sec.URG] = bool(headerData[13] & 0x20)
    result[Sec.ACK] = bool(headerData[13] & 0x10)
    result[Sec.PSH] = bool(headerData[13] & 0x08)
    result[Sec.RST] = bool(headerData[13] & 0x04)
    result[Sec.SYN] = bool(headerData[13] & 0x02)
    result[Sec.FIN] = bool(headerData[13] & 0x01)
    result[Sec.recvWin] = int.from_bytes(headerData[14:16], byteorder='big', signed=False)
    result[Sec.checksum] = int.from_bytes(headerData[16:18], byteorder='big', signed=False)
    result[Sec.urgPtr] = int.from_bytes(headerData[18:20], byteorder='big', signed=False)
    return result


def add_int_to_bytearray(array: bytearray, ele: int, length: int):
    for byte in int.to_bytes(ele, byteorder='big', length=length):
        array.append(byte)


def dict_to_header(headerDict: dict):
    result = bytearray(20)
    result[0:2] = int.to_bytes(headerDict[Sec.sPort], length=2, byteorder='big')
    result[2:4] = int.to_bytes(headerDict[Sec.dPort], length=2, byteorder='big')
    result[4:8] = int.to_bytes(headerDict[Sec.seqNum], length=4, byteorder='big')
    result[8:12] = int.to_bytes(headerDict[Sec.ackNum], length=4, byteorder='big')
    result[12] = ((headerDict[Sec.offset] << 4) | headerDict[Sec.NS])
    result[13] = (headerDict[Sec.CWR] << 7 | headerDict[Sec.ECE] << 6 |
                  headerDict[Sec.URG] << 5 | headerDict[Sec.ACK] << 4 |
                  headerDict[Sec.PSH] << 3 | headerDict[Sec.RST] << 2 |
                  headerDict[Sec.SYN] << 1 | headerDict[Sec.FIN])
    result[14:16] = int.to_bytes(headerDict[Sec.recvWin], length=2, byteorder='big')
    result[16:18] = int.to_bytes(headerDict[Sec.checksum], length=2, byteorder='big')
    result[18:20] = int.to_bytes(headerDict[Sec.urgPtr], length=2, byteorder='big')
    return result


def set_header_checksum(header: bytearray, checksum: bytearray):
    header[16:18] = checksum


def ip_to_bytes(ip: str):
    return bytes(map(int, ip.split('.')))


# This function should be called before sending each rUDP segment,
# its functionality is calculate and fill in the checksum in header
# using 1's complement
def fill_checksum(header: bytearray, data: bytearray):
    checksum = 0
    header[16:18] = [0x00, 0x00]
    for i in range(0, len(header), 2):
        val = ~int.from_bytes(header[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = (((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff))
    for i in range(0, len(data), 2):
        val = ~int.from_bytes(data[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    if len(data) % 2 != 0:
        pad = bytearray([data[-1], 0x00])
        val = ~int.from_bytes(pad, byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    logger.debug('fill checksum: %d' % checksum)
    set_header_checksum(header, bytearray(int.to_bytes(checksum, byteorder='big', length=2, signed=False)))


# Check the data using checksum from the header
def check_header_checksum(data: bytearray):
    checksum = 0
    for i in range(0, len(data), 2):
        val = ~int.from_bytes(data[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    if len(data) % 2 != 0:
        pad = bytearray([data[-1], 0x00])
        val = ~int.from_bytes(pad, byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    result = ((checksum & 0x0000ffff) == 0x0000ffff or checksum == 0)
    if not result:
        logger.debug("header checksum error. Received: %d" % checksum)
    return result


def get_seq_num(header: bytearray):
    return int.from_bytes(header[4:8], byteorder='big', signed=False)


def get_ack_num(header: bytearray):
    return int.from_bytes(header[8:12], byteorder='big', signed=False)




MAX_BUFFER_SIZE = 153600
# Each data packet should be of size 1k
PACKET_SIZE = 5120

# 512kb receive window, store with a array
class rcvBuffer:
    def __init__(self):
        self.buffer = bytearray(MAX_BUFFER_SIZE)
        self.lastByteRead = 0
        self.lastByteRcvd = 0
        self.length = 0
        # Lock buffer when accessing
        self.lock = threading.Lock()

    def add(self, data: bytearray):
        self.lock.acquire()
        try:
            if self.length + PACKET_SIZE > MAX_BUFFER_SIZE:
                return False    # buffer overflow

            self.buffer[self.lastByteRcvd:self.lastByteRcvd+PACKET_SIZE] = data
            self.lastByteRcvd += PACKET_SIZE
            if self.lastByteRcvd == MAX_BUFFER_SIZE:
                self.lastByteRcvd = 0
            self.length += PACKET_SIZE
            return True
        finally:
            self.lock.release()    

    def get_win(self):
        return (MAX_BUFFER_SIZE - self.length) // PACKET_SIZE


    def peek(self):
        if self.length == 0:
            raise Exception('Reading an empty buffer.')
        return self.buffer[self.lastByteRead: self.lastByteRead + PACKET_SIZE]


    def pop(self):
        self.lock.acquire()
        try:
            result = self.peek()
            self.lastByteRead += PACKET_SIZE
            if self.lastByteRead == MAX_BUFFER_SIZE:
                self.lastByteRead = 0
            self.length -= PACKET_SIZE
            logger.debug('%d %d', self.lastByteRcvd // PACKET_SIZE, self.lastByteRead // PACKET_SIZE)
            return result
        finally:
            self.lock.release()

# 512kb sending window, store with a array
class sndBuffer:
    def __init__(self):
        self.buffer = bytearray(MAX_BUFFER_SIZE)
        self.messages = {}
        self.lastByteSent = 0
        self.lastByteAcked = 0
        self.lastByteReady = 0
        self.length = 0
        self.win = 0
        self.cwnd = 0
        self.state = CwndState.SHAKING
        self.pausing = False
        self.ssthresh = 0
        self.adding = True
        # Lock buffer when accessing
        self.lock = threading.Lock()

    def find_cong(self):
        #self.pausing = True
        if self.state != CwndState.SHAKING and self.state == CwndState.CONGAVOID:
            self.state = CwndState.SLOWSTART
            self.ssthresh = self.cwnd // 2
            self.cwnd = 1


    def get_data(self):
        datalist = []
        i = self.lastByteSent
        #logger.debug("pausing: %d" % self.pausing)
        if self.length == 0:
            return []
        count = 0
        while count < self.win:
            datalist.append(self.buffer[i:i+PACKET_SIZE])
            i += PACKET_SIZE
            if i == MAX_BUFFER_SIZE:
                i = 0
            if i == self.lastByteReady:
                break
            count += 1
        return datalist

    def get_win(self):
        return self.win

    def get_cwnd(self):
        return self.cwnd
        
    def set_cwnd(self, cwnd):
        self.lock.acquire()
        try:
            self.cwnd = cwnd
        finally:
            self.lock.release()

    def set_win(self, win):
        self.lock.acquire()
        try:
            if win > 10:
                win = 10
            self.win = win
        finally:
            self.lock.release()

    def add(self, data: bytearray):
        self.lock.acquire()
        try:
            logger.debug('adding')
            if self.length + PACKET_SIZE > MAX_BUFFER_SIZE:
                logger.debug("%d %d %d %d %d" % (self.lastByteAcked // PACKET_SIZE, self.lastByteSent //PACKET_SIZE,
        self.lastByteReady // PACKET_SIZE, self.length // PACKET_SIZE, self.win))
                self.adding = False
                return True
            self.buffer[self.lastByteReady:self.lastByteReady+PACKET_SIZE] = data
            self.lastByteReady += PACKET_SIZE
            if self.lastByteReady == MAX_BUFFER_SIZE:
                self.lastByteReady = 0
            self.length += PACKET_SIZE
            return False
        finally:
            self.lock.release()    
    
    def ack(self, mess):
        self.lock.acquire()
        logger.debug('%s' % str(self.state))
        try:
            if self.state == CwndState.SLOWSTART:
                logger.debug('%d %d %d', self.lastByteAcked // PACKET_SIZE, self.lastByteSent // PACKET_SIZE, self.lastByteReady // PACKET_SIZE)
                if self.lastByteAcked in self.messages and self.messages[self.lastByteAcked].seqNum == mess.seqNum:
                    if self.messages[self.lastByteAcked].is_acked() is True:
                        self.cwnd += 1
                        if self.cwnd == self.ssthresh:
                            self.state = CwndState.CONGAVOID
                        self.lastByteAcked += PACKET_SIZE
                else:
                    return False
                if self.lastByteAcked == MAX_BUFFER_SIZE:
                    self.lastByteAcked = 0
                self.length -= PACKET_SIZE
            else:
                last = 0
                if self.messages[self.lastByteAcked].seqNum == mess.seqNum:
                    self.lastByteAcked += PACKET_SIZE
                    if self.lastByteAcked == MAX_BUFFER_SIZE:
                        self.lastByteAcked = 0
                logger.debug('%d %d %d %d', self.lastByteAcked // PACKET_SIZE, self.lastByteSent // PACKET_SIZE, self.lastByteReady // PACKET_SIZE, self.length // PACKET_SIZE)
                if self.lastByteSent == 0:
                    last = MAX_BUFFER_SIZE - PACKET_SIZE
                else:
                    last = self.lastByteSent - PACKET_SIZE
                if self.messages[last].is_acked() is True:
                    self.cwnd += 1
                    self.lastByteAcked = self.lastByteSent
                    if self.lastByteReady >= self.lastByteAcked:
                        self.length = self.lastByteReady - self.lastByteAcked
                    else:
                        self.length = MAX_BUFFER_SIZE + self.lastByteReady - self.lastByteAcked
                else:
                    return False
        finally:
            self.lock.release()

    def send(self, mess):
        self.lock.acquire()
        try:
            self.messages[self.lastByteSent] = mess
            self.lastByteSent += PACKET_SIZE
            if self.lastByteSent == MAX_BUFFER_SIZE:
                self.lastByteSent = 0
        finally:
            self.lock.release()


MAX_TIMER_COUNT = 32


class message:
    def __init__(self, data, conn: rUDPConnection, sendBuf: sndBuffer=None):
        self.acked = False
        self.data = data
        self.seqNum = int.from_bytes(data[4:8], byteorder='big', signed=False)
        self.conn = conn
        self.sendBuf = sendBuf
        # initial time out is 1000 ms
        self.timeoutTime = 1
        self.timeoutCount = 0

    def is_acked(self):
        return self.acked

    def send_with_timer(self, destAddr):
        if self.timeoutCount == 3:
            logger.warning('Timeout %d exceeds 3 times' % self.seqNum)
        if self.timeoutCount == 20:
            logger.error('Too many timeout, dropping packet %d' % self.seqNum)
        if not self.acked:
            if self.timeoutCount != 0:
                logger.debug('Resending message with seqNum=%d' % self.seqNum)
                self.sendBuf.find_cong()
            self.send(destAddr)
            t = threading.Timer(self.timeoutTime, self.send_with_timer, args=[destAddr])
            self.timeoutCount += 1
            t.start()
        else:
            logger.debug('Message with seqNum=%d finished' % self.seqNum)


    def send(self, destAddr):
        self.conn.socket.sendto(self.data, destAddr)





class msgPool:
    def __init__(self):
        self.messages = {}
        self.lock = threading.Lock()


    def add_msg(self, msg: message, expectACK):
        try:
            self.lock.acquire()
            self.messages[expectACK] = msg
        finally:
            self.lock.release()

    def get_mess(self, ackNum):
        if ackNum in self.messages:
            return self.messages[ackNum]
        return None

    def ack_msg(self, ackNum):
        if ackNum in self.messages:
            self.messages[ackNum].acked = True
            logger.debug('ACKed message with ackNum: %d' % ackNum)

    # ack all messages with ackNum smaller than or equal to the given ackNum
    def ack_to_num(self, ackNum):
        try:
            self.lock.acquire()
            to_pop = []
            for key in self.messages:
                if key <= ackNum:
                    self.ack_msg(key)
                    to_pop.append(key)
            for k in to_pop:
                self.messages.pop(k)
        finally:
            self.lock.release()

    



