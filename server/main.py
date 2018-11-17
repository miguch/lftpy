from reliableUDP.server import rUDPServer


def main():
    conn = rUDPServer("127.0.0.1", 8899)


if __name__ == "__main__":
    main()

