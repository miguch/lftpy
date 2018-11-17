from reliableUDP.connection import rUDPConnection


class rUDPClient(rUDPConnection):
    def __init__(self, ip, port):
        super(rUDPClient, self).__init__(ip, port)
        pass

