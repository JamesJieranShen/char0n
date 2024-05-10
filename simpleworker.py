# Does not require a router, directly connects to the clients.
# https://zguide.zeromq.org/docs/chapter4/#Client-Side-Reliability-Lazy-Pirate-Pattern
# by Daniel Lundin <dln(at)eintr(dot)org>, MIT license

import zmq
import time
from chroma_handler import ChromaHandler
import sys
import argparse

from config import *

if __name__ == "__main__":
    try:
        context = zmq.Context(IO_THREADS)
        socket = context.socket(zmq.REP)
        address = f"tcp://*:{frontend_port}"
        socket.bind(address)
        print(f"Connected to {address}")
        # socket.bind("ipc:///tmp/chroma")
        parser = argparse.ArgumentParser(
            prog="simpleworker.py",
            description="Run a single GPU worker without a backend socket.",
        )
        parser.add_argument('--async_mode', action='store_true')
        parser.add_argument('--outdir')
        args = parser.parse_args()
        use_async = args.async_mode
        print("Running in {} mode".format(("asynchronous") if use_async else "synchronous"))
        chroma_handler = ChromaHandler(geometry_pickle, async_mode=use_async, outdir=args.outdir)
        while True:
            frames = socket.recv_multipart()
            if not frames:
                break
            header = frames[0]
            if header == PING:
                print(f"I: Received ping from client")
                socket.send_multipart([ACK])
                continue
            reply = chroma_handler.respond_to_zmq_request(frames)
            socket.send_multipart(reply)
    except KeyboardInterrupt:
        print("I: Received keyboard interrupt")
        print("I: Closing socket")
        socket.close()
        context.term()
        exit(0)
