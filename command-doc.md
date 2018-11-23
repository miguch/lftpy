# LFTP application Commands

Every Packet sent should have 1024 bytes data parts, the first 4 bytes in the data
should indicate the actual length of the packet, the rest of the packet should be padded with \0.

1. client->server: `HELLO LFTP`
create a client-server application connection

2. client->server: `lLIST`
server will returns the list of files on server as a JSON formatted string

3. client->server: `lGET filename`
request a file from server

4. client->server: `lSEND filename`
request the server to be ready for accepting a file with certain filename.

5. server->client: `NOTEXIST filename`
returns this command when the file requested by client is not available

6. server->client: `EXISTED filename`
returns when file said to be sent from client is already existed in the server.

7. server->client: `WAITING filename`
returns when the server is ready to receive the file

8. server->client: `SENDING filename`
returns when the server is ready to send the file to client

9. client<->server: `SIZE filesize`
Send this command before sending file, indicating the size of the file.

10. client<->server: `DONE`
Returns this command when a file has been completely sent.

