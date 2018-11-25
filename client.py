import argparse
import re
import threading
import socket
import os
import sys
import json
from enum import Enum
from reliableUDP.lftplog import logger
from reliableUDP.client import rUDPClient
from reliableUDP.application import app

clientStates = Enum('clientStates', ('CLOSED', 'SENDREQUEST', 'DATA'))
operations = Enum('operations', ('GET', 'SEND', 'LIST'))

commands = {
    'lsend': operations.SEND,
    'lget': operations.GET,
    'ls': operations.LIST
}

class client(app):
    def __init__(self, serverIP, serverPort, action, filename):
        app.__init__(self)
        self.lock = threading.Lock()
        self.lock.acquire()
        self.serverIP = serverIP
        self.serverPort = serverPort
        self.action = action
        self.filename = filename
        self.rudp = rUDPClient(app=self)
        self.state = clientStates.CLOSED
        self.waitingList = []
        self.file = None
        self.fileSize = 0
        try:
            if self.action == operations.SEND:
                self.file = open(filename, 'rb')
        except FileNotFoundError as e:
            print(e)
            sys.exit()
        finally:
            self.lock.release()
        self.rudp.connect(self.serverIP, self.serverPort)

    def close(self):
        self.rudp.finished = True
        if self.file:
            self.file.close()
        sys.exit()

    def update_state(self, newState):
        logger.debug('Client application new state: %s' % str(newState))
        self.state = newState

    def send_data(self, data, useBuffer):
        buf = bytearray(1024)
        length = len(data)
        buf[0:4] = int.to_bytes(length, length=4, byteorder='big')
        buf[4:4+length] = data
        pad_len = 1024 - 4 - length
        buf[4+length:1024] = b'\0' * pad_len
        if useBuffer:
            if not self.rudp.append_snd_buffer(buf):
                self.waitingList.append(buf)
                return False
        else:
            self.rudp.send_msg(buf)
        return True

    def send_request(self):
        if self.action == operations.GET:
            self.send_data(b'lGET %s' % bytes(self.filename, encoding='utf-8'), False)
        elif self.action == operations.SEND:
            self.send_data(b'lSEND %s' % bytes(self.filename, encoding='utf-8'), False)
        elif self.action == operations.LIST:
            self.send_data(b'lLIST', False)


    def next(self, user=None):
        try:
            self.lock.acquire()
            if self.state == clientStates.CLOSED:
                self.update_state(clientStates.SENDREQUEST)
                self.send_request()
                logger.info('Sending request to server')
            elif self.state == clientStates.DATA:
                if len(self.waitingList) != 0:
                    while len(self.waitingList) != 0:
                        if self.rudp.append_snd_buffer(self.waitingList[0]):
                            self.waitingList.pop(0)
                        else:
                            return
                if self.action == operations.SEND:
                    while True and not self.file.closed:
                        data = self.file.read(1020)
                        print('\rUploaded %.2f%%.' % (float(self.file.tell()) * 100 / self.fileSize), end='')
                        if self.file.tell() == self.fileSize:
                            print('\rFile upload completed')
                        if len(data) == 0:
                            break
                        else:
                            # Pause when we cannot add new data to send
                            if not self.send_data(data, True):
                                break
        finally:
            self.lock.release()


    def process_data(self, user=None):
        goNext = False
        try:
            self.lock.acquire()
            data = self.rudp.consume_rcv_buffer()
            length = int.from_bytes(data[:4], byteorder='big')
            content = data[4:4+length]
            if self.state == clientStates.SENDREQUEST:
                if self.action == operations.SEND:
                    [cmd, arg] = content.split(b' ')
                    if cmd == b'EXISTED' and content[len(cmd)+1:].decode() == self.filename:
                        print('File already existed on the server!')
                        self.rudp.finish_conn()
                    elif cmd == b'WAITING' and content[len(cmd)+1:].decode() == self.filename:
                        print('Sending the file now...')
                        self.update_state(clientStates.DATA)
                        logger.info('server waiting for file')
                        # send file size
                        begin_pos = self.file.tell()
                        self.file.seek(0, os.SEEK_END)
                        self.fileSize = self.file.tell()
                        self.file.seek(begin_pos, os.SEEK_SET)
                        self.send_data(b'SIZE ' + int.to_bytes(self.fileSize, byteorder='little', length=4), False)
                        goNext = True
                elif self.action == operations.LIST:
                    files = json.loads(content.decode())
                    for name in files:
                        print(name, end=' ')
                    print()
                    self.update_state(clientStates.DATA)
                elif self.action == operations.GET:
                    [cmd, arg] = content.split(b' ')
                    if cmd.decode() == 'NOTEXIST' and content[len(cmd)+1:].decode() == self.filename:
                        print('Requested file does not exist on the server!')
                        self.rudp.finish_conn()
                    elif cmd.decode() == 'SIZE':
                        self.file = open(self.filename, 'wb')
                        self.fileSize = int.from_bytes(arg, byteorder='little')
                        print('Receiving the file now ..., size: %d' % self.fileSize)
                        self.update_state(clientStates.DATA)
            elif self.state == clientStates.DATA:
                if (self.file is None or self.file.closed or self.file.tell() == self.fileSize) and content.decode() == 'DONE':
                    self.rudp.finish_conn()
                elif self.action == operations.GET:
                    self.file.write(content)
                    print('\rDownloaded %.2f%%.' % ((float(self.file.tell()) * 100) / self.fileSize), end='')
                    if self.file.tell() == self.fileSize:
                        print('\rFile downloade completed')
        finally:
            self.lock.release()
            if goNext:
                self.next()

    def notify_close(self):
        self.close()

    def remove_user(self, user):
        # Not implement since there is no "User" in a client
        pass





def main():
    parser = argparse.ArgumentParser(description='The client program of LFTP')
    parser.add_argument('command', type=str, help='Use lsend, lget or ls to instruct LFTP operation.')
    parser.add_argument('ServerAddr', type=str, help='The ip or domain address and the port of the LFTP server')
    parser.add_argument('filename', type=str, nargs='?', help='The file you wish to get or send.', default=None)
    args = parser.parse_args()
    args.command = args.command.lower()
    cmd = None
    if args.command in commands:
        cmd = commands[args.command]
    else:
        print('Invalid command %s' % args.command)
        return 
    ip = ""
    port = ""
    domain = ""
    if re.match('^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]):\d{1,5}$', args.ServerAddr):
        # ip address
        ip = args.ServerAddr[:args.ServerAddr.index(':')]
        port = int(args.ServerAddr[args.ServerAddr.index(':')+1:])
    elif re.match('^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|([a-zA-Z0-9][a-zA-Z0-9-_]{1,61}[a-zA-Z0-9]))\.([a-zA-Z]{2,6}|[a-zA-Z0-9-]{2,30}\.[a-zA-Z]{2,8}):\d{1,5}', args.ServerAddr):
        # domain name
        domain = args.ServerAddr[:args.ServerAddr.index(':')]
        port = int(args.ServerAddr[args.ServerAddr.index(':')+1:])
        ip = socket.gethostbyname(domain)
    else:
        print('The Server Address (%s) is invalid!' % args.ServerAddr)
        return
    print("target server is %s, port: %d" % (ip, port))
    if (cmd == operations.GET or cmd == operations.SEND) and args.filename == None:
        print("A file name must be specified for lget and lsend!")
        return
    cli = client(ip, port, cmd, args.filename)

if __name__ == "__main__":
    main()

