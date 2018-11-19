import threading
from .connection import rUDPConnection, message
from .utilities import *
from .lftplog import logger
import random


class serverConn:
    def __init__(self, addr, conn):
        # addr is the target address
        self.addr = addr
        self.destIP, self.destPort = addr
        self.conn = conn
        self.state = RecvStates.LISTEN
        self.seqNum = 0
        self.clientSeq = 0
        self.messages = msgPool()
        self.recvWindow = circleBuffer()
        logger.debug('Create a server connection to %s' % str(addr))

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def handshake(self):
        # random seq
        self.seqNum = random.randint(0, 2 ** 16)
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq + 1,
            Sec.SYN: 1,
            Sec.ACK: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("Server Second handshake sent, seq: " + str(self.seqNum))
        syn_msg = message(headerData, self.conn)
        syn_msg.send_with_timer(self.addr)
        self.update_state(RecvStates.SYN_REVD)
        self.seqNum += 1
        self.clientSeq += 1
        self.recvWindow.baseSeq = self.clientSeq

    def response_FIN(self):
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq,
            Sec.SYN: 0,
            Sec.ACK: 1,
            Sec.FIN: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("Server FIN message sent, seq: " + str(self.seqNum))
        fin_msg = message(headerData, self.conn)
        fin_msg.send_with_timer(self.addr)
        self.update_state(RecvStates.LAST_ACK)
        self.seqNum += 1
        self.clientSeq += 1
        self.messages.add_msg(fin_msg, self.seqNum)

    def process_data(self, data, headerDict: dict):
        if not check_header_checksum(data):
            logger.debug('Header checksum check failed.')
            return
        if headerDict[Sec.ACK]:
            self.messages.ack_to_num(headerDict[Sec.ackNum])
            if self.state == RecvStates.SYN_REVD:
                self.update_state(RecvStates.ESTABLISHED)
        else:
            if len(data) - defaultHeaderLen != PACKET_SIZE:
                logger.debug('Received data with invalid length, discarded')
                return
            # Normal data message
            if headerDict[Sec.seqNum] == self.clientSeq:
                if self.recvWindow.length + PACKET_SIZE < MAX_BUFFER_SIZE:
                    logger.debug('Added data %d to buffer' % headerDict[Sec.seqNum])
                    self.recvWindow.add(data[defaultHeaderLen+1:])
                    self.clientSeq += PACKET_SIZE
                    self.ack_message()
        if headerDict[Sec.FIN] and self.state == RecvStates.ESTABLISHED:
            self.update_state(RecvStates.CLOSE_WAIT)
            # Client closing connection
            self.response_FIN()

    def send_msg(self, data):
        pass


    # Send the ack message to client
    def ack_message(self):
        headerDict = defaultHeaderDict.copy().update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq,
            Sec.SYN: 0,
            Sec.ACK: 1,
            Sec.FIN: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("sent ack message, ackNum: " + str(self.clientSeq))
        ack_msg = message(headerData, self.conn)
        ack_msg.send(self.addr)


class rUDPServer:
    def __init__(self, ip, port, application):
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
            self.connections[addr] = serverConn(addr, self.conn)
            self.connections[addr].clientSeq = headerDict[Sec.seqNum]
        else:
            self.connections[addr].process_data(data, headerDict)
