# LFTP

LFTP is a UDP based application that provides the functionality of sending file with reliable data transfer. 

## Usage

1. Server

   ```shell
   python3 server.py [-h] [-p PORT] [-a ADDR] [-d DATADIR]
   ```

2. Client

   ```shell
   python3 client.py [-h] {ls|lsend|lget} ServerAddr [filename]
   ```

## Document

Please refer to `lftpDocument.md ` to see the document on the classes and methods implemented in LFTP.