import json
import asyncio
import socket
import sqlalchemy

import database.manipulate as sql

from workspace import workspace

from websockets.asyncio.server import serve

from modules.logging import logger

from database.models import Users

from functools import partial

sqlEngine = sqlalchemy.create_engine(workspace.getConfigAttribute("RestlessDatabaseFilePath"))

connections = {}

log: logger = logger("websocket-proxy-service.log", "INFO")

async def sendToReverseProxy(message, reader, writer):
    writer.write(message.encode())
    await writer.drain()

    data = await reader.read(1024)

    return data.decode()

async def proxyServer(websocket, reader, writer):
    async for message in websocket:
        event = json.loads(message)

        userFound: bool = sql.checkIfUserExists(sqlEngine, 
                                                event["username"], event["pincode"])
        if not userFound:
            await websocket.close()
            return

        response = await sendToReverseProxy(event["data"], reader, writer)

        log.info(f"Data received :: {event['data']} . . .")

        if len(response) > 0:
            await websocket.send(response)
            log.info(f"Response sent back :: {response} . . .")

async def main() -> None:
    log.info("Started")
    proxyReader, proxyWriter = await asyncio.open_connection("127.0.0.1", 12444)
    async with serve(partial(proxyServer, reader=proxyReader, writer=proxyWriter), "127.0.0.1", 13000):
        await asyncio.get_running_loop().create_future()
    log.info("Finished")

def runMain():
    asyncio.run(main())

if __name__ == "__main__":
    runMain()
