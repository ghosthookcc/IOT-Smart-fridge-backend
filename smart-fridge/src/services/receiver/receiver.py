import socket

from workspace import *

from modules.logger import logger

from queue import LifoQueue
from enum import Enum

import threading
from threading import Thread

from database.models import db, Users
from database.manipulate import insertSensorValue
from sqlalchemy import insert

class Tag(str, Enum):
    SENSOR = "SENSOR"
    TYPE = "TYPE"

class ClientState(Enum):
    IDLE = 0
    RUNNING = 1
    DISCONNECTED = 2

log: logger = logger("receiver-service.log", "INFO")

class Message:
    def __init__(self,
                 data) -> None:
        self.data: str = data
        self.headers: dict = {}
        self.create()

    def create(self) -> None:
        headersStart: int = self.data.find("<")
        headersEnd: int   = self.data.find(">")
        if headersStart != -1 and headersEnd != -1:
            tmpData: str = self.data[headersStart+1:headersEnd]
            headerTags = tmpData.split(";")
            for tag in headerTags:
                tag = tag.split("=")
                if len(tag) == 2:
                    self.headers[tag[0]] = tag[1]
        self.data = self.data[headersEnd+1:]


class ServerConnectionHandler(Thread):
    inData: LifoQueue = LifoQueue()
    def __init__(self,
                 connection: socket,
                 address: str,
                 packetReadMaxSize: int = 1024):
        Thread.__init__(self)
        self.daemon = True

        self.connection = connection
        self.address = address
        self.maxReadPerPacketInBytes = packetReadMaxSize

        self.state = ClientState.IDLE

    def run(self):
        dataHandler = Thread(target = self.interpretData, daemon=True)
        dataHandler.start()

        self.state = ClientState.RUNNING
        while True:
            self.receive()

    def receive(self):
        data: str = self.connection.recv(self.maxReadPerPacketInBytes)
        if not data:
            self.state = ClientState.DISCONNECTED
            return

        log.info(f"Incoming RAW data :: {data} . . .")

        buffer: str = ""
        buffer += data.decode()
        while not buffer.endswith("<END>"):
            buffer += self.connection.recv(self.maxReadPerPacketInBytes).decode()
        for bufferData in buffer.split("<END>"):
            if len(bufferData) > 0:
                newMessage: Message = Message(bufferData)
                self.inData.put(newMessage)

    def interpretData(self):
        while True:
            if not self.inData.empty():
                message = self.inData.get()

                log.info(f"Received data :: {message.data} . . .")
                for tag, value in message.headers.items():
                    match tag:
                        case Tag.SENSOR:
                            sensorGuid = message.headers["ID"]
                            sensorType = value
                            sensorValue = self.data
                            insertSensorValue(sensorGuid,
                                              sensorType,
                                              sensorValue)
                        case Tag.TYPE:
                            if value == "ping":
                                self.connection.send("pong".encode())
                    log.info(f"Received Tag :: {tag} with a value of {value} . . .")
                self.inData.task_done()

class ServerSocket:
    def __init__(self, 
                 host: str = "0.0.0.0", port: int = 12444,
                 localHost: str = "127.0.0.1", localPort: int = 12445) -> None:
        self.receiver = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.host = host
        self.port = port

        self.localHost = localHost
        self.localPort = localPort

        self.clients = []

    def removeDisconnectedClients(self) -> None:
        for client in self.clients:
            if (client.state == ClientState.DISCONNECTED):
                self.clients.remove(client)
        threading.Timer(15, self.removeDisconnectedClients).start()

    def handleNewConnection(self) -> None:
        clientSocket, address = self.receiver.accept()

        log.info(f"Received new connection on {address} . . .")

        receiver: ServerConnectionHandler = ServerConnectionHandler(clientSocket, address)
        self.clients.append(receiver)
        receiver.start()

    def start(self,
              maxConnections: int) -> None:
        self.receiver.bind((self.host, self.port))
        self.receiver.listen(maxConnections)

        log.info(f"Server bound to {self.host}:{self.port} . . .")
        log.info(f"Server device GUID is {guid()} . . .")

        while True:
            self.removeDisconnectedClients()
            self.handleNewConnection()

def main() -> None:
    server: ServerSocket = ServerSocket()
    server.start(5)

if __name__ == "__main__":
    main()
