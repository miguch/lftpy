from enum import Enum
from reliableUDP.connection import *
import threading

# noinspection PyArgumentList
RecvStates = Enum('RecvStates', ('CLOSED', 'LISTEN', 'SYN_REVD',
                                 'ESTABLISHED', 'CLOSE_WAIT', 'LAST_ACK'))

# noinspection PyArgumentList
SendStates = Enum('SendStates', ('CLOSED', 'SYN_SENT', 'ESTABLISHED',
                                 'FIN_WAIT_1', 'FIN_WAIT_2', 'TIME_WAIT'))

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
    result[Sec.CWR] = bool(headerData[13] * 0x80)
    result[Sec.ECE] = bool(headerData[13] * 0x40)
    result[Sec.URG] = bool(headerData[13] * 0x20)
    result[Sec.ACK] = bool(headerData[13] * 0x10)
    result[Sec.PSH] = bool(headerData[13] * 0x08)
    result[Sec.RST] = bool(headerData[13] * 0x04)
    result[Sec.SYN] = bool(headerData[13] * 0x02)
    result[Sec.FIN] = bool(headerData[13] * 0x01)
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
# source ip and dest ip is needed for pseudo header
def fill_checksum(header: bytearray, data: bytearray, sIP: bytearray, dIP: bytearray):
    checksum = 0
    pseudoHeader = bytearray([*sIP, *dIP, 0x00, 0x11])
    pseudoHeader += int.to_bytes(len(header)+len(data), length=2, byteorder='big', signed=False)
    for i in range(0, 12, 2):
        val = ~int.from_bytes(pseudoHeader[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = (((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff))
    for i in range(0, int(len(header) / 2), 2):
        val = ~int.from_bytes(header[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = (((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff))
    for i in range(0, int(len(data) / 2), 2):
        val = ~int.from_bytes(data[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    if len(data) % 2 != 0:
        pad = bytearray([data[-1], 0x00])
        val = ~int.from_bytes(pad, byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    set_header_checksum(header, bytearray(int.to_bytes(checksum, byteorder='big', length=2, signed=False)))


# Check the data using checksum from the header
# source ip and dest ip is needed for pseudo header
def check_header_checksum(data: bytearray, sIP: bytearray, dIP: bytearray):
    checksum = 0
    pseudoHeader = bytearray([*sIP, *dIP, 0x00, 0x11])
    pseudoHeader += int.to_bytes(len(data), length=2, byteorder='big', signed=False)
    for i in range(0, 12, 2):
        val = ~int.from_bytes(pseudoHeader[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = (((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff))
    for i in range(0, int(len(data) / 2), 2):
        val = ~int.from_bytes(data[i:i+2], byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    if len(data) % 2 != 0:
        pad = bytearray([data[-1], 0x00])
        val = ~int.from_bytes(pad, byteorder='big', signed=False) & 0x0000ffff
        checksum = (val + checksum)
        checksum = ((checksum & 0xffff0000) >> 16) + (checksum & 0x0000ffff)
    return (checksum & 0x0000ffff) == 0


def get_seq_num(header: bytearray):
    return int.from_bytes(header[4:8], byteorder='big', signed=False)


def get_ack_num(header: bytearray):
    return int.from_bytes(header[8:12], byteorder='big', signed=False)


class msgPool:
    def __init__(self):
        self.messages = {}

    def add_msg(self, msg: message, expectACK):
        self.messages[expectACK] = msg

    def ack_msg(self, ackNum):
        if ackNum in self.messages:
            self.messages[ackNum].acked = True
            self.messages.pop(ackNum)
            logger.debug('ACKed message with ackNum: %d' % ackNum)

    # ack all messages with ackNum smaller than or equal to the given ackNum
    def ack_to_num(self, ackNum):
        for key in self.messages:
            if key <= ackNum:
                self.ack_msg(key)


MAX_BUFFER_SIZE = 524288
# Each data packet should be of size 1k
PACKET_SIZE = 1024

# 512kb receive window, store with a array
class circleBuffer:
    def __init__(self):
        self.buffer = bytearray(MAX_BUFFER_SIZE)
        self.baseIndex = 0
        self.baseSeq = 0
        self.endIndex = 0
        self.length = 0
        # Lock buffer when accessing
        self.lock = threading.Lock()

    def add(self, data: bytearray):
        if self.length + PACKET_SIZE > MAX_BUFFER_SIZE:
            raise Exception('buffer overflow when adding data.')
        
        self.buffer[self.endIndex:self.endIndex+PACKET_SIZE] = data
        self.endIndex += PACKET_SIZE
        if self.endIndex == MAX_BUFFER_SIZE:
            self.endIndex = 0
        self.length += PACKET_SIZE

    def peek(self):
        if self.length == 0:
            raise Exception('Reading an empty buffer.')
        return self.buffer[self.baseIndex: self.baseIndex + PACKET_SIZE]


    def pop(self):
        result = self.peek()
        self.baseIndex += PACKET_SIZE
        if self.baseIndex == MAX_BUFFER_SIZE:
            self.baseIndex = 0
        self.length -= PACKET_SIZE
        self.baseSeq += PACKET_SIZE
        return result

