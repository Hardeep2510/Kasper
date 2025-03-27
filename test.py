import logging
import socket
import math
import loop as asyncio

log = logging.getLogger("loop.server")


async def handle_client(client):
    loop = asyncio.get_event_loop()
    request = None
    while request != "quit":
        request = (await loop.sock_recv(client, 255)).decode("utf8")
        response = str(eval(request)) + "\n"
        await loop.sock_sendall(client, response.encode("utf8"))
    log.info("goodbye")
    client.close()
    return "client handling complete"


async def primes(start, stop):
    def is_prime(num):
        if num <= 1:
            return False
        for i in range(2, int(math.sqrt(num)) + 1):
            if num % i == 0:
                return False
        return True

    return list(filter(is_prime, range(start, stop)))


async def run_server():
    result = await primes(1, 10)
    log.info("got: %s", result)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("localhost", 8888))
    server.listen(8)
    server.setblocking(False)

    loop = asyncio.get_event_loop()

    while True:
        log.debug("accepting")
        result = await loop.sock_accept(server)
        assert result, result
        client, _address = result
        log.debug("accepted")
        log.debug("handling client")
        loop.create_task(handle_client(client))

if __name__ == '__main__':
    asyncio.run(run_server())
