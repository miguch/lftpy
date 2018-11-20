from .connection import rUDPConnection, message
from .lftplog import logger
from .utilities import *
from .application import app
import random


class rUDPClient:
    def __init__(self, ip, app):
        self.conn = rUDPConnection(ip, 0)
        self.ip = self.conn.ip
        self.port = self.conn.port
        self.state = SendStates.CLOSED
        self.destIP = ""
        self.destPort = 0
        self.seqNum = 0
        self.serverSeq = 0
        self.canSend = True
        self.messages = msgPool()
        self.recvWin = rcvBuffer()
        self.app = app

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def establish_conn(self):
        # random seq in first handshake
        self.seqNum = random.randint(0, 2 ** 16)
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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
        if not self.canSend:
            return False
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq,
            Sec.SYN: 0,
            Sec.ACK: 0,
            Sec.FIN: 0,
            Sec.recvWin: self.recvWin.getWin()
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, data)
        logger.debug("data message sent, seq: " + str(self.seqNum))
        data_msg = message(headerData + data, self.conn)
        data_msg.send_with_timer((self.destIP, self.destPort))
        self.seqNum += len(data)
        self.messages.add_msg(data_msg, self.seqNum)

    # initiate Client's first wavehand, fourth wavehand is triggered when the second 
    # and third wavehand are received from server.
    def finish_conn(self):
        logger.debug('Closing connection.')
        self.first_wavehand()


    def first_wavehand(self):
        logger.debug('Sending first wave header')
        self.seqNum = self.seqNum + 1
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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

    def second_wavehand(self):
        logger.debug('Second wave hand received from server')
        self.update_state(SendStates.FIN_WAIT_2)

    def third_wavehand(self):
        logger.debug('Third wave hand received from server')
        self.update_state(SendStates.TIME_WAIT)
        self.fourth_wavehand()

    def close(self):
        self.conn.socket.close()
        self.update_state(SendStates.CLOSED)

    def fourth_wavehand(self):
        logger.debug('Sending first wave header')
        self.seqNum = self.seqNum + 1
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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
        close_thread = threading.Timer(30, self.close)
        close_thread.start()

    def process_msg(self, data):
        if check_header_checksum(data):
            logger.debug('received a packet with invalid checksum')
        headerDict = header_to_dict(data)
        if headerDict[Sec.ACK]:
            # ack message
            self.messages.ack_to_num(headerDict[Sec.ackNum])
            if headerDict[Sec.ackNum] == self.seqNum and self.state == SendStates.FIN_WAIT_1:
                self.second_wavehand()
            elif self.state == SendStates.FIN_WAIT_2 and headerDict[Sec.FIN]:
                self.third_wavehand()
            else:
                if headerDict[Sec.recvWin] > 0:
                    self.canSend = True
                else:
                    self.canSend = False
        else:
            # normal data
            if headerDict[Sec.seqNum] == self.serverSeq:
                if self.recvWin.getWin() > 0:
                    logger.debug('add data with seq %d to receiving window' % headerDict[Sec.seqNum])
                    self.recvWin.add(data[defaultHeaderLen+1:])
                    self.serverSeq += PACKET_SIZE
                    self.ack_msg()
                else:
                    logger.debug('Discard packet %d: rcvWindow full' % headerDict[Sec.seqNum])
                    headerDict = defaultHeaderDict.copy()
                    headerDict.update({
                        Sec.sPort: self.port,
                        Sec.dPort: self.destPort,
                        Sec.ACK: 1,
                        Sec.SYN: 0,
                        Sec.recvWin: self.recvWin.getWin()
                    })
                    headerData = dict_to_header(headerDict)
                    fill_checksum(headerData, bytearray())
                    win_msg = message(headerData, self.conn)
                    win_msg.send((self.destIP, self.destPort))
            else:
                logger.debug('Discarded packet %d not arrived in order' % headerDict[Sec.seqNum])        

    def ack_msg(self):
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq,
            Sec.SYN: 0,
            Sec.ACK: 1,
            Sec.FIN: 1
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("sent ack message, ackNum: " + str(self.serverSeq))
        ack_msg = message(headerData, self.conn)
        ack_msg.send((self.destIP, self.destPort))
    
    # Start a thread for this function after establishing connection 
    def listen_msg(self):
        while True:
            data, addr = self.conn.socket.recvfrom(2048)
            if addr != (self.destIP, self.destPort):
                logger.debug('Received message from unexpected sender')
                continue
            else:
                processor = threading.Thread(target=self.process_msg, args=[data])
                processor.start()
