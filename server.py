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
    'lSEND': operations.GET,
    'lGET': operations.SEND,
    'lLIST': operations.LIST
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

    def send_data(self, data):
        buf = bytearray(1024)
        length = len(data)
        buf[0:4] = int.to_bytes(length, length=4, byteorder='big')
        buf[4:4+length] = data
        pad_len = 1024 - 4 - length
        buf[4+length:1024] = b'\0' * pad_len
        if not self.conn.append_snd_buffer(buf):
            self.waitingList.append(buf)
            return False
        return True

    def next(self):
        if self.state == serverStates.DATA:
            if len(self.waitingList) != 0:
                while len(self.waitingList) != 0:
                    if self.rudp.append_snd_buffer(self.waitingList[0]):
                        self.waitingList.pop(0)
                    else:
                        return
            if self.action == operations.GET:
                while True:
                    data = self.file.read(1020)
                    if len(data) == 0:
                        self.send_data(b'DONE')
                        break
                    else:
                        # Pause when we cannot add new data to send
                        if not self.send_data(data):
                            break

    def response_req(self):
        if self.action == operations.GET:
            # getting file from client
            try:
                self.file = open(os.path.join(self.dir, self.filename), 'rb')
                self.file.seek(0, os.SEEK_END)
                self.fileSize = self.file.tell()
                self.file.seek(0, os.SEEK_SET)
                self.send_data(b'SIZE ' + int.to_bytes(self.fileSize, byteorder='little', length=4))
                self.send_file()
                self.update_state(serverStates.DATA)
            except FileNotFoundError as e:
                self.send_data(b'NOTEXIST %s' % self.filename)
                self.send_data(b'DONE')
        elif self.action == operations.LIST:
            fileList = os.listdir(self.dir)
            response = bytearray(json.dumps(fileList), encoding='utf-8')
            self.send_data(response)
            self.send_data(b'DONE')
        elif self.action == operations.SEND:
            # Sending file to client
            checker = Path(os.path.join(self.dir, self.filename))
            if checker.exists():
                self.send_data(b'EXISTED %s' % self.filename)
                self.send_data(b'DONE')
            self.file = open(os.path.join(self.dir, self.filename), 'wb')
            self.update_state(serverStates.WAIT_SIZE)
            self.send_data(b'WAITING %s' % self.filename)

    def process_data(self, data):
        if self.action == operations.SEND:
            if self.state == serverStates.WAIT_SIZE:
                [cmd, arg] = data.split(' ')
                if cmd == 'SIZE':
                    self.fileSize = int.from_bytes(arg, byteorder='little')
                    self.update_state(serverStates.DATA)
            elif self.state == serverStates.DATA:
                try:
                    self.lock.acquire()
                    self.file.write(data)
                    if self.file.tell() == self.fileSize:
                        self.send_data(b'DONE')
                finally:
                    self.lock.release()
            

class server(app):
    def __init__(self, ip, port, dataDir):
        app.__init__(self)
        self.ip = ip
        self.port = port
        self.dir = dataDir
        self.rudp = rUDPServer(self.ip, self.port, self)
        self.sessions = {}

    def next(self, user):
        sessions[user].next()

    def process_data(self, user):
        data = self.rudp.connections[user].consume_rcv_buffer()
        length = int.from_bytes(data[:4], bytearray='big')
        content = data[4:4+length]
        if user not in self.sessions:
            req = content.split(' ')
            if req[0] in commands:
                action = commands[req[0]]
                self.sessions[user] = serverSession(user[0], user[1], action, self.dir, rudp.connections[user])
                if len(req) > 1:
                    self.sessions[user].filename = req[1]
                self.sessions[user].response_req()
        else:
            self.sessions[user].process_data(content)
            

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


if __name__ == "__main__":
    main()

