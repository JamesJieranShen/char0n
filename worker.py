## Adapted from 
#
# https://zguide.zeromq.org/docs/chapter4/#Robust-Reliable-Queuing-Paranoid-Pirate-Pattern 
# by Daniel Lundin <dln(at)eintr(dot)org>, MIT license

import time, zmq
from config import *
from chroma_handler import ChromaHandler
import numpy as np


def worker_socket(context, poller):
    """Helper function that returns a new configured socket
       connected to the Paranoid Pirate queue"""
    worker = context.socket(zmq.DEALER) # DEALER
    poller.register(worker, zmq.POLLIN)
    worker.connect(f"tcp://localhost:{backend_port}")
    worker.send(READY)
    return worker

if __name__ == "__main__":
    chroma_handler = ChromaHandler(geometry_pickle)
    context = zmq.Context(IO_THREADS)
    poller = zmq.Poller()
    liveness = HEARTBEAT_LIVENESS
    retries_left = WORKER_RECONNECT_ATTEMPTS

    heartbeat_at = time.time() + HEARTBEAT_INTERVAL

    worker = worker_socket(context, poller)
    while True:
        socks = dict(poller.poll(HEARTBEAT_INTERVAL * 1000))
        if socks.get(worker) == zmq.POLLIN:  # Received a message from router
            # Get message
            frames = worker.recv_multipart()
            if not frames:
                break
            if len(frames) > 1:  # Normal simulation request
                reply = chroma_handler.respond_to_zmq_request(frames)
                worker.send_multipart(reply)
                liveness = HEARTBEAT_LIVENESS
            elif len(frames) == 1 and frames[0] == HEARTBEAT:
                # print("I: Received heartbeat from router")
                liveness = HEARTBEAT_LIVENESS
            if retries_left < WORKER_RECONNECT_ATTEMPTS:
                print("I: Reconnected to queue")
                retries_left = WORKER_RECONNECT_ATTEMPTS
        else:  # No messagereceived
            liveness -= 1
            if liveness == 0:
                print("W: Lost connection to router!")
                print(f"W: Reconnecting in {WORKER_RETRY_AFTER} seconds...")
                time.sleep(WORKER_RETRY_AFTER)
                if retries_left == 0:
                    print("E: Worker cannot reconnect to queue")
                    break
                # Re-intialize a worker socket
                poller.unregister(worker)
                worker.setsockopt(zmq.LINGER, 0)
                worker.close()
                worker = worker_socket(context, poller)
                liveness = HEARTBEAT_LIVENESS
                retries_left -= 1
        if time.time() > heartbeat_at:
            worker.send(HEARTBEAT)
            heartbeat_at = time.time() + HEARTBEAT_INTERVAL


