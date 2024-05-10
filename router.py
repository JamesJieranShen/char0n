## Adapted from 
#
# https://zguide.zeromq.org/docs/chapter4/#Robust-Reliable-Queuing-Paranoid-Pirate-Pattern 
# by Daniel Lundin <dln(at)eintr(dot)org>, MIT license

from collections import OrderedDict
import time
import zmq

from config import *

class Worker(object):
    def __init__(self, address):
        self.address = address
        self.expiry = time.time() + HEARTBEAT_INTERVAL * HEARTBEAT_LIVENESS

    def __repr__(self):
        return f"<Worker:, {self.address}: expire {self.expiry}>"
    
class WorkerQueue(object):
    def __init__(self):
        self.queue = OrderedDict()

    def ready(self, worker):
        self.queue.pop(worker.address, None)
        self.queue[worker.address] = worker

    def purge(self):
        """Look for & kill expired workers."""
        t = time.time()
        expired = []
        for address, worker in self.queue.items():
            if t > worker.expiry:  # Worker expired
                expired.append(address)
        for address in expired:
            print("W: Idle worker expired: %s" % address)
            self.queue.pop(address, None)

    def next(self):
        if len(self.queue) == 0:
            return None
        address, worker = self.queue.popitem(False)
        return address


if __name__ == "__main__":
    context = zmq.Context(IO_THREADS)
    frontend = context.socket(zmq.ROUTER)
    backend = context.socket(zmq.ROUTER)
    frontend.bind(f"tcp://*:{frontend_port}")
    backend.bind(f"tcp://*:{backend_port}")
    poller = zmq.Poller()
    poller.register(backend, zmq.POLLIN)
    poller.register(frontend, zmq.POLLIN)
    workers = WorkerQueue()
    heartbeat_at = time.time() + HEARTBEAT_INTERVAL
    
    while True:
        try:
            print(f"I: Current active workers: {len(workers.queue)}" )
            socks = dict(poller.poll(HEARTBEAT_INTERVAL * 1000))
            if socks.get(backend) == zmq.POLLIN:
                # Handle worker activity on backend
                # Use worker address for LRU routing
                frames = backend.recv_multipart()
                if not frames:
                    break
                address = frames[0]
                workers.ready(Worker(address))
                # Validate control message, or return reply to client
                msg = frames[1:]
                if len(msg) == 1:
                    if msg[0] == READY:
                        print(f"I: Worker {address} is ready")
                    elif msg[0] == HEARTBEAT:
                        pass
                        # print(f"I: Worker {address} heartbeat")
                    else:
                        print("E: Invalid message from worker: %s" % msg)
                else:
                    
                    frontend.send_multipart(msg)
                    
                # Send heartbeats to idle workers if it's time
                if time.time() >= heartbeat_at:
                    for worker in workers.queue:
                        msg = [worker, HEARTBEAT]
                        backend.send_multipart(msg)
                    heartbeat_at = time.time() + HEARTBEAT_INTERVAL

            if socks.get(frontend) == zmq.POLLIN:
                # Get next client request, route to next worker
                frames = frontend.recv_multipart()
                client_address = frames[0]
                header = frames[2]
                if header == PING:  # Do not consult workers when ping is received, just reply
                    print(f"I: Received ping from {client_address}")
                    frontend.send_multipart([client_address, DELIMITER, ACK])
                    continue
                # Received a normal request, forward to the workers
                print(f"I: Received request! Address: {frames[0]} Header: {frames[2]}")
                if not frames:
                    break
                worker_address = workers.next()
                if worker_address:
                    frames.insert(0, worker_address)
                    backend.send_multipart(frames)
                else:
                    print("W: No workers available")
                    frontend.send_multipart([client_address, DELIMITER, NO_WORKERS])

            # Purge expired workers
            workers.purge()
        except KeyboardInterrupt:
            print("W: Interrupted, attempting to gracefully shut down...")
            print("W: Press Ctrl+C again to force quit.")
            backend.close()
            frontend.close()
            context.term()
            print("Goodbye!")
            exit(0)