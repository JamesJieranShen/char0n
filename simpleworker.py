# Does not require a router, directly connects to the clients.
# https://zguide.zeromq.org/docs/chapter4/#Client-Side-Reliability-Lazy-Pirate-Pattern
# by Daniel Lundin <dln(at)eintr(dot)org>, MIT license

import zmq
import time
from chroma_handler import ChromaHandler

from config import *

if __name__ == "__main__":
    try:
        context = zmq.Context(IO_THREADS)
        socket = context.socket(zmq.REP)
        socket.bind(f"tcp://*:{frontend_port}")
        chroma_handler = ChromaHandler(geometry_pickle)
        while True:
            frames = socket.recv_multipart()
            if not frames:
                break
            header = frames[0]
            if header == PING:
                print(f"I: Received ping from client")
                socket.send_multipart([PONG])
                continue
            reply = chroma_handler.respond_to_zmq_request(frames)
            socket.send_multipart(reply)
    except KeyboardInterrupt:
        print("I: Received keyboard interrupt")
        print("I: Closing socket")
        socket.close()
        context.term()
        exit(0)