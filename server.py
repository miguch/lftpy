import argparse
import re
from reliableUDP.server import rUDPServer
from reliableUDP.application import app


class serverSession:
    def __init__(self, destIP, destPort):
        self.destIP = destIP
        self.destPort = destPort

    def process_data(self, user):
        pass

    

class server(app):
    def __init__(self, ip, port):
        app.__init__()
        self.ip = ip
        self.port = port
        self.rudp = rUDPServer(self.ip, self.port, self)
        self.sessions = {}

    def next(self, user):
        pass

    def process_data(self, user):
        pass

    def notify_remove_user(self, user):
        pass



def main():
    parser = argparse.ArgumentParser(description='The server program of LFTP')
    parser.add_argument('-p', '--port', type=int, default=9999)
    parser.add_argument('-a', '--addr', default='0.0.0.0')
    args = parser.parse_args()
    if not re.match('^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))$', args.addr):
        print('The ip address is invalid!')
        return
    if args.port > 65535 or args.port <= 0:
        print('The port number is invalid')
        return
    print('The address to listen on is %s:%d' % (args.addr, args.port))
    lftp_server = server(args.addr, args.port)


if __name__ == "__main__":
    main()

