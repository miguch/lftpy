from enum import Enum

# noinspection PyArgumentList
RecvStates = Enum('RecvStates', ('CLOSED', 'LISTEN', 'SYN_REVD',
                                 'ESTABLISHED', 'CLOSE_WAIT', 'LAST_ACK'))

# noinspection PyArgumentList
SendStates = Enum('SendStates', ('CLOSED', 'SYN_SENT', 'ESTABLISHED',
                                 'FIN_WAIT_1', 'FIN_WAIT_2', 'TIME_WAIT'))

#The sections in TCP header
# noinspection PyArgumentList
Sec = Enum('headerStruct', ('sPort', 'dPort', 'seqNum', 'ackNum',
                                       'offset', 'NS', 'CWR', 'ECE', 'URG',
                                       'ACK', 'PSH', 'RST', 'SYN', 'FIN',
                                       'recvWin', 'checksum', 'urgPtr'))


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
    result = bytearray()
    add_int_to_bytearray(result, headerDict[Sec.sPort], 2)
    add_int_to_bytearray(result, headerDict[Sec.dPort], 2)
    add_int_to_bytearray(result, headerDict[Sec.seqNum], 4)
    add_int_to_bytearray(result, headerDict[Sec.ackNum], 4)
    result.append((headerDict[Sec.offset] << 4) | headerDict[Sec.NS])
    result.append(headerDict[Sec.CWR] << 7 | headerDict[Sec.ECE] << 6 |
                  headerDict[Sec.URG] << 5 | headerDict[Sec.ACK] << 4 |
                  headerDict[Sec.PSH] << 3 | headerDict[Sec.RST] << 2 |
                  headerDict[Sec.SYN] << 1 | headerDict[Sec.FIN])
    add_int_to_bytearray(result, headerDict[Sec.recvWin], 2)
    add_int_to_bytearray(result, headerDict[Sec.checksum], 2)
    add_int_to_bytearray(result, headerDict[Sec.urgPtr], 2)
    return result




