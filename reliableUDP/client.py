from .connection import rUDPConnection
from .lftplog import logger
from .utilities import *
from .application import app
import random
import socket

class rUDPClient:
    def __init__(self, app):
        self.conn = rUDPConnection("0.0.0.0", 0)
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
        self.recvEmpty = False
        self.sendWin = sndBuffer()
        self.app = app
        self.finished = False
        self.listener = None
        self.seqLock = threading.Lock()
        self.ackLock = threading.Lock()

    def consume_rcv_buffer(self):
        if self.recvWin.get_win() == 0:
            headerDict = defaultHeaderDict.copy()
            headerDict.update({
                Sec.sPort: self.port,
                Sec.dPort: self.destPort,
                Sec.ackNum: 0,
                Sec.seqNum: self.seqNum,
                Sec.ACK: 1,
                Sec.SYN: 0,
                Sec.recvWin: 1
            })
            headerData = dict_to_header(headerDict)
            fill_checksum(headerData, bytearray())
            win_msg = message(headerData, self.conn)
            win_msg.send((self.destIP, self.destPort))
        data = self.recvWin.pop()
        return data

    # for app to use
    def append_snd_buffer(self, data: bytearray):
        full = self.sendWin.add(data)
        if full:
            if self.sendWin.lastByteSent == self.sendWin.lastByteReady:
                self.check_cong_and_send()
            return False    # sending buffer cannot add for now
        if self.sendWin.get_cwnd() == 0:  # first file trunk
            self.sendWin.set_cwnd(1)
            self.sendWin.set_win(1)
            self.sendWin.ssthresh = 10
            self.sendWin.state = CwndState.SLOWSTART
            self.check_cong_and_send()
        return True
        
    def check_cong_and_send(self):
        datalist = self.sendWin.get_data()
        if not datalist:
            self.app.notify_next_move((self.destIP, self.destPort))
            return
        if datalist[0] == 1:
            return
        for data in datalist:
            self.send_msg(data)
        self.app.notify_next_move((self.destIP, self.destPort))


    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def establish_conn(self):
        # random seq in first handshake
        self.seqNum = random.randint(1, 2 ** 16)
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
        syn_msg = message(headerData, self.conn, self.sendWin)
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
        syn_msg.send((self.destIP, self.destPort))
        self.messages.add_msg(syn_msg, self.seqNum+1)
        self.update_state(SendStates.ESTABLISHED)
        self.app.notify_next_move()
        # Start listening message
        self.listener = threading.Thread(target=self.listen_msg, daemon=True)
        self.listener.start()
        self.listener.join()


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
        self.serverSeq = headerDict[Sec.seqNum] + 1
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
        self.seqLock.acquire()
        try:
            headerDict = defaultHeaderDict.copy()
            headerDict.update({
                Sec.sPort: self.conn.port,
                Sec.dPort: self.destPort,
                Sec.seqNum: self.seqNum,
                Sec.ackNum: self.serverSeq,
                Sec.SYN: 0,
                Sec.ACK: 0,
                Sec.FIN: 0,
                Sec.recvWin: self.recvWin.get_win()
            })
            headerData = dict_to_header(headerDict)
            fill_checksum(headerData, data)
            logger.debug("data message sent, seq: " + str(self.seqNum))
            data_msg = message(headerData + data, self.conn, self.sendWin)
            data_msg.send_with_timer((self.destIP, self.destPort))
            self.seqNum += len(data)
            self.messages.add_msg(data_msg, self.seqNum)
            if self.sendWin.state != CwndState.SHAKING:
                self.sendWin.send(data_msg)
        finally:
            self.seqLock.release()


    # initiate Client's first wavehand, fourth wavehand is triggered when the second 
    # and third wavehand are received from server.
    def finish_conn(self):
        logger.debug('Closing connection.')
        self.first_wavehand()
        self.app.notify_close()


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
        syn_msg = message(headerData, self.conn, self.sendWin)
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
        if not check_header_checksum(data):
            logger.debug('received a packet with invalid checksum')
        headerDict = header_to_dict(data)
        self.ackLock.acquire()
        try:
            if headerDict[Sec.ACK]:
                # ack message
                mess = self.messages.get_mess(headerDict[Sec.ackNum])
                if mess is not None:
                    self.messages.ack_to_num(headerDict[Sec.ackNum])
                    logger.debug('Received ack message with ackNum=%d' % headerDict[Sec.ackNum])
                    if headerDict[Sec.ackNum] == self.seqNum and self.state == SendStates.FIN_WAIT_1:
                        self.second_wavehand()
                    elif self.state == SendStates.FIN_WAIT_2 and headerDict[Sec.FIN]:
                        self.third_wavehand()
                    else:
                        if self.sendWin.state != CwndState.SHAKING:
                            if headerDict[Sec.recvWin] > 0:
                                if headerDict[Sec.ackNum] > 0:
                                    flag = self.sendWin.ack(mess)
                                    self.sendWin.set_win(min(headerDict[Sec.recvWin], self.sendWin.get_cwnd()))
                                    if flag is not False:
                                        self.check_cong_and_send()
                                else:
                                    self.check_cong_and_send()
            else:
                if len(data) - defaultHeaderLen != PACKET_SIZE:
                    logger.debug('Received data with invalid length, discarded')
                    return
                # normal data
                if headerDict[Sec.seqNum] == self.serverSeq:

                    if self.recvWin.get_win() > 0:
                        logger.debug('add data with seq %d to receiving window' % headerDict[Sec.seqNum])
                        flag = self.recvWin.add(data[defaultHeaderLen:])
                        if flag:
                            self.serverSeq += PACKET_SIZE
                            self.ack_msg()
                        self.app.notify_process_data()
                    if self.recvWin.get_win() == 0:
                        logger.debug('rcvWindow full')
                        headerDict = defaultHeaderDict.copy()
                        headerDict.update({
                            Sec.sPort: self.port,
                            Sec.dPort: self.destPort,
                            Sec.seqNum: self.seqNum,
                            Sec.ackNum: 0,
                            Sec.ACK: 1,
                            Sec.SYN: 0,
                            Sec.recvWin: self.recvWin.get_win()
                        })
                        headerData = dict_to_header(headerDict)
                        fill_checksum(headerData, bytearray())
                        win_msg = message(headerData, self.conn)
                        win_msg.send((self.destIP, self.destPort))
                elif headerDict[Sec.seqNum] <= self.serverSeq:
                    self.ack_msg()
                else:
                    logger.debug('Discarded packet %d not arrived in order, Expecting: %d' % (headerDict[Sec.seqNum], self.serverSeq))
        finally:
            self.ackLock.release()

    def ack_msg(self):
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.serverSeq,
            Sec.SYN: 0,
            Sec.ACK: 1,
            Sec.FIN: 0,
            Sec.recvWin: self.recvWin.get_win()
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("sent ack message, ackNum: " + str(self.serverSeq))
        ack_msg = message(headerData, self.conn)
        ack_msg.send((self.destIP, self.destPort))
    
    # Start a thread for this function after establishing connection 
    def listen_msg(self):
        self.conn.socket.settimeout(1)
        while not self.finished:
            try:
                data, addr = self.conn.socket.recvfrom(6144)
                if addr != (self.destIP, self.destPort):
                    logger.debug('Received message from unexpected sender')
                    continue
                else:
                    processor = threading.Thread(target=self.process_msg, args=[data], daemon=True)
                    processor.start()
            except socket.timeout:
                continue
