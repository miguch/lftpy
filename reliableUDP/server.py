import threading
import random
from .connection import rUDPConnection
from .utilities import *
from .lftplog import logger

class serverConn:
    def __init__(self, addr, conn, app, server):
        # addr is the target address
        self.addr = addr
        self.destIP, self.destPort = addr
        self.conn = conn
        self.state = RecvStates.LISTEN
        self.seqNum = 0
        self.clientSeq = 0
        self.app = app
        self.messages = msgPool()
        self.recvWin = rcvBuffer()
        self.sendWin = sndBuffer()
        self.canSend = True
        self.server = server
        logger.debug('Create a server connection to %s' % str(addr))

    def consume_rcv_buffer(self):
        if self.recvWin.get_win() == 0:
            headerDict = defaultHeaderDict.copy()
            headerDict.update({
                Sec.sPort: self.conn.port,
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
            return False    #sending buffer cannot add for now
        if self.sendWin.get_cwnd() == 0:  #first file trunk
            self.sendWin.set_cwnd(1)
            self.sendWin.set_win(1)
            self.sendWin.ssthresh = 8
            self.sendWin.state = CwndState.SLOWSTART
            self.check_cong_and_send()
        return True

    def check_cong_and_send(self):
        datalist = self.sendWin.get_data()
        if not datalist:
            return
        for data in datalist:
            self.send_msg(data)
        if self.sendWin.adding is False:
            self.app.notify_next_move((self.destIP, self.destPort))

    def update_state(self, newState):
        logger.debug("State: %s->%s" % (self.state, newState))
        self.state = newState

    def handshake(self):
        # random seq
        self.seqNum = random.randint(1, 2 ** 16)
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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
        syn_msg = message(headerData, self.conn, self.sendWin)
        syn_msg.send_with_timer(self.addr)
        self.update_state(RecvStates.SYN_REVD)
        self.seqNum += 1
        self.clientSeq += 1
        self.recvWin.baseSeq = self.clientSeq
        self.messages.add_msg(syn_msg, self.seqNum)

    def response_FIN(self):
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
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
        fin_msg = message(headerData, self.conn, self.sendWin)
        fin_msg.send(self.addr)
        self.update_state(RecvStates.LAST_ACK)
        self.seqNum += 1
        self.clientSeq += 1
        self.messages.add_msg(fin_msg, self.seqNum)
        

    def process_data(self, data, headerDict: dict):
        if not check_header_checksum(data):
            logger.debug('Header checksum check failed.')
            return
        if headerDict[Sec.ACK]:
            mess = self.messages.get_mess(headerDict[Sec.ackNum])
            if mess is not None:
                logger.debug('Received ack message with ackNum=%d' % headerDict[Sec.ackNum])
                self.messages.ack_to_num(headerDict[Sec.ackNum])
                if self.state == RecvStates.SYN_REVD:
                    self.update_state(RecvStates.ESTABLISHED)
                else:
                    if self.sendWin.state != CwndState.SHAKING:
                        self.sendWin.set_win(min(headerDict[Sec.recvWin], self.sendWin.get_cwnd()))
                        if headerDict[Sec.recvWin] > 0:
                            if headerDict[Sec.ackNum] > 0:
                                self.sendWin.ack(mess)
                                self.check_cong_and_send()
                            else:
                                self.check_cong_and_send()
        else:
            if len(data) - defaultHeaderLen != PACKET_SIZE:
                logger.debug('Received data with invalid length, discarded')
                return
            # Normal data message
            if headerDict[Sec.seqNum] == self.clientSeq:
                if self.recvWin.get_win() > 0:
                    logger.debug('add data with seq %d to receiving window' % headerDict[Sec.seqNum])
                    flag = self.recvWin.add(data[defaultHeaderLen:])
                    if flag:
                        self.clientSeq += PACKET_SIZE
                        self.ack_message()
                        data = self.recvWin.peek()
                        self.app.notify_process_data((self.destIP, self.destPort))

                if self.recvWin.get_win() == 0:
                    logger.debug('rcvWindow full')
                    headerDict = defaultHeaderDict.copy()
                    headerDict.update({
                        Sec.sPort: self.conn.port,
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
            elif headerDict[Sec.seqNum] <= self.clientSeq:
                self.ack_message()
            else:
                logger.debug('Discarded packet %d not arrived in order, Expecting: %d' % (headerDict[Sec.seqNum], self.clientSeq))
        if headerDict[Sec.FIN] and self.state == RecvStates.ESTABLISHED:
            self.update_state(RecvStates.CLOSE_WAIT)
            # Client closing connection
            self.response_FIN()
            self.removeSelf()
            self.app.remove_user((self.destIP, self.destPort))

    def send_msg(self, data):
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq,
            Sec.SYN: 0,
            Sec.ACK: 0,
            Sec.FIN: 0,
            Sec.recvWin: self.recvWin.get_win()
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, data)
        logger.debug("data message sent, seq: " + str(self.seqNum))
        data_msg = message(headerData + data, self.conn, self.sendWin)
        data_msg.send_with_timer(self.addr)
        self.seqNum += len(data)
        self.messages.add_msg(data_msg, self.seqNum)
        if self.sendWin.state != CwndState.SHAKING:
            self.sendWin.send(data_msg)


    # Send the ack message to client
    def ack_message(self):
        headerDict = defaultHeaderDict.copy()
        headerDict.update({
            Sec.sPort: self.conn.port,
            Sec.dPort: self.destPort,
            Sec.seqNum: self.seqNum,
            Sec.ackNum: self.clientSeq,
            Sec.SYN: 0,
            Sec.ACK: 1,
            Sec.FIN: 1,
            Sec.recvWin: self.recvWin.get_win()
        })
        headerData = dict_to_header(headerDict)
        fill_checksum(headerData, bytearray())
        logger.debug("sent ack message, ackNum: " + str(self.clientSeq))
        ack_msg = message(headerData, self.conn)
        ack_msg.send(self.addr)


    def removeSelf(self):
        self.server.removeConn(self.addr)


class rUDPServer:
    def __init__(self, ip, port, app):
        self.conn = rUDPConnection(ip, port)
        # The server will identify each connection with
        # a tuple of clients' address and port
        self.connections = {}
        self.app = app
        self.listener = threading.Thread(target=self.recv_msg, daemon=True)
        self.listener.start()
        # Infinite listen loop

    def recv_msg(self):
        while True:
            data, addr = self.conn.socket.recvfrom(2048)
            recv_thread = threading.Thread(target=self.process_recv_msg, args=[data, addr], daemon=True)
            recv_thread.start()

    def process_recv_msg(self, data, addr):
        headerDict = header_to_dict(data)
        if headerDict[Sec.SYN] and not headerDict[Sec.ACK]:
            # First handshake
            self.connections[addr] = serverConn(addr, self.conn, self.app, self)
            self.connections[addr].clientSeq = headerDict[Sec.seqNum]
            self.connections[addr].handshake()
        else:
            if addr in self.connections:
                self.connections[addr].process_data(data, headerDict)
            else:
                logger.debug('Received message from unexpected sender')

    def removeConn(self, addr):
        self.connections.pop(addr)
