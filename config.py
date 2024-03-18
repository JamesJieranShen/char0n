## Connection Parameters
frontend_port = "5555"
backend_port = "5556"

geometry_pickle = "detector.pkl"

HEARTBEAT_LIVENESS = 3    # Time of heartbeats missed before server considers client dead
HEARTBEAT_INTERVAL = 1.0  # Seconds
WORKER_RETRY_AFTER = 2.0  # Seconds
WORKER_RECONNECT_ATTEMPTS = 3  # Number of times to retry sending a message to a worker

IO_THREADS = 1  # Official recommendation is 1 thread per gbps of send+receive

## Protocal Constants
READY = b"\x01"
HEARTBEAT = b"\x02"
PING = b"PING"
PONG = b"PONG"
DELIMITER = b""
SIM_COMPLETE = b"SIM_COMPLETE"
SIM_FAILED = b"SIM_FAILED"
NO_WORKERS = b"NO_WORKERS"
PHOTONDATA = b"PHOTONDATA"
DETECTOR_INFO = b"DETECTOR_INFO"
UNKNOWN_REQUEST = b"UNKNOWN_REQUEST"
N_DATABLOCKS = 13