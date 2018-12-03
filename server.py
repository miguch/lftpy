import argparse
import re
import threading
import os
import json
from pathlib import Path
from enum import Enum
from reliableUDP.lftplog import logger
from reliableUDP.server import rUDPServer, serverConn
from reliableUDP.application import app

serverStates = Enum('serverStates', ('RECVREQUEST', 'WAIT_SIZE', 'DATA'))
operations = Enum('operations', ('GET', 'SEND', 'LIST'))


commands = {
    b'lSEND': operations.SEND,
    b'lGET': operations.GET,
    b'lLIST': operations.LIST
}

class serverSession:
    def __init__(self, destIP, destPort, action, dataDir, conn: serverConn):
        self.lock = threading.Lock()
        self.lock.acquire()
        self.destIP = destIP
        self.destPort = destPort
        self.action = action
        self.state = serverStates.RECVREQUEST
        self.conn = conn
        self.filename = None
        self.dir = dataDir
        self.file = None
        self.fileSize = 0
        self.waitingList = []
        self.lock.release()


    def update_state(self, newState):
        logger.info('User %s:%d switch to state %s' % (self.destIP, self.destPort, newState))
        self.state = newState

    def send_data(self, data, useBuffer):
        buf = bytearray(5120)
        length = len(data)
        buf[0:4] = int.to_bytes(length, length=4, byteorder='big')
        buf[4:4+length] = data
        pad_len = 5120 - 4 - length
        buf[4+length:5120] = b'\0' * pad_len
        if useBuffer:
            if not self.conn.append_snd_buffer(buf):
                self.waitingList.append(buf)
                return False
        else:
            self.conn.send_msg(buf)
        return True

    def next(self):
        self.lock.acquire()
        try:
            if self.state == serverStates.DATA:
                if len(self.waitingList) != 0:
                    while len(self.waitingList) != 0:
                        if self.conn.append_snd_buffer(self.waitingList[0]):
                            self.waitingList.pop(0)
                        else:
                            return
                if self.action == operations.GET:
                    while True and not self.file.closed:
                        data = self.file.read(5116)
                        if len(data) == 0:
                            self.send_data(b'DONE', True)
                            self.file.close()
                            break
                        else:
                            # Pause when we cannot add new data to send
                            if not self.send_data(data, True):
                                break
        finally:
            self.lock.release()

    def response_req(self):
        if self.action == operations.GET:
            # getting file from client
            try:
                logger.info('Client %s:%d requested file %s' % (self.destIP, self.destPort, self.filename))
                self.file = open(os.path.join(self.dir, self.filename.decode()), 'rb')
                self.file.seek(0, os.SEEK_END)
                self.fileSize = self.file.tell()
                self.file.seek(0, os.SEEK_SET)
                self.send_data(b'SIZE ' + int.to_bytes(self.fileSize, byteorder='little', length=4), False)
                self.update_state(serverStates.DATA)
                self.next()
            except FileNotFoundError as e:
                self.send_data(b'NOTEXIST %s' % self.filename, False)
        elif self.action == operations.LIST:
            fileList = os.listdir(self.dir)
            response = bytearray(json.dumps(fileList), encoding='utf-8')
            self.send_data(response, False)
            self.send_data(b'DONE', False)
        elif self.action == operations.SEND:
            # Sending file to client
            checker = Path(os.path.join(self.dir, self.filename.decode()))
            if checker.exists():
                self.send_data(b'EXISTED %s' % self.filename, False)
                return
            logger.info('User %s:%d request to upload file %s' % (self.destIP, self.destPort, self.filename))
            self.file = open(os.path.join(self.dir, self.filename.decode()), 'wb')
            self.update_state(serverStates.WAIT_SIZE)
            self.send_data(b'WAITING %s' % self.filename, False)

    def process_data(self, data):
        if self.action == operations.SEND:
            if self.state == serverStates.WAIT_SIZE:
                msg = data.split(b' ')
                if len(msg) < 2:
                    return
                [cmd, arg] = msg
                if cmd == b'SIZE':
                    self.fileSize = int.from_bytes(arg, byteorder='little')
                    self.update_state(serverStates.DATA)
            elif self.state == serverStates.DATA:
                try:
                    self.lock.acquire()
                    if self.file.closed:
                        return
                    if self.file.tell() == self.fileSize:
                        return
                    self.file.write(data)
                    print(self.file.tell() / self.fileSize)
                    if self.file.tell() == self.fileSize:
                        self.send_data(b'DONE', False)
                        self.file.close()
                finally:
                    self.lock.release()
            

class server(app):
    def __init__(self, ip, port, dataDir):
        try:
            app.__init__(self)
            self.lock = threading.Lock()
            self.lock.acquire()
            self.ip = ip
            self.port = port
            self.dir = dataDir
            self.rudp = rUDPServer(self.ip, self.port, self)
            self.sessions = {}
        finally:
            self.lock.release()

    def next(self, user):
        if user in self.sessions:
            self.sessions[user].next()

    def process_data(self, user):
        try:
            self.lock.acquire()
            data = self.rudp.connections[user].consume_rcv_buffer()
            length = int.from_bytes(data[:4], byteorder='big')
            content = data[4:4+length]
            if user not in self.sessions:
                req = bytes(content).split(b' ')
                if req[0] in commands:
                    action = commands[req[0]]
                    self.sessions[user] = serverSession(user[0], user[1], action, self.dir, self.rudp.connections[user])
                    if len(req) > 1:
                        self.sessions[user].filename = content[len(req[0])+1:]
                    self.sessions[user].response_req()
            else:
                self.sessions[user].process_data(content)
        finally:
            self.lock.release()
            

    def remove_user(self, user):
        self.sessions.pop(user)

    def notify_close(self, user):
        #Not implement
        pass



def main():
    parser = argparse.ArgumentParser(description='The server program of LFTP')
    parser.add_argument('-p', '--port', type=int, default=9999, help='The port to listen on')
    parser.add_argument('-a', '--addr', default='0.0.0.0', help='The ip address to listen on')
    parser.add_argument('-d', '--datadir', default='.', help='The data directory of the server')
    args = parser.parse_args()
    if not re.match('^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))$', args.addr):
        print('The ip address is invalid!')
        return
    if args.port > 65535 or args.port <= 0:
        print('The port number is invalid')
        return
    print('The address to listen on is %s:%d' % (args.addr, args.port))
    lftp_server = server(args.addr, args.port, args.datadir)
    lftp_server.rudp.listener.join()


if __name__ == "__main__":
    main()

