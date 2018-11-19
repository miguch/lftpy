from reliableUDP.server import rUDPServer
from application import application

class server:
    pass

def main():
    conn = rUDPServer("127.0.0.1", 8899, server())


if __name__ == "__main__":
    main()

