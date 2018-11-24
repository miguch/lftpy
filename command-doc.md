# LFTP application Commands

Every Packet sent should have 1024 bytes data parts, the first 4 bytes in the data
should indicate the actual length of the packet, the rest of the packet should be padded with \0.

1. client->server: `lLIST`
server will returns the list of files on server as a JSON formatted array string

2. client->server: `lGET filename`
request a file from server

3. client->server: `lSEND filename`
request the server to be ready for accepting a file with certain filename.

4. server->client: `NOTEXIST filename`
returns this command when the file requested by client is not available

5. server->client: `EXISTED filename`
returns when file said to be sent from client is already existed in the server.

6. server->client: `WAITING filename`
returns when the server is ready to receive the file

7. client<->server: `SIZE filesize`
Send this command before sending file, indicating the size of the file.

8. server->client: `DONE`
The server will send this command when an action has been completed.

