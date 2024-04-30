# ChAR0N: Chroma And Rat 0mq Network

The idea behind this package is to allow Chroma to run as a server that responds to simulation requests. This allows
users to run their Geant4 simulations completely decoupled from the Chroma instance, in separate containers or even
separate machines on the same network. 

### SimpleWorker
The Simple worker acts as a single worker that can be used to run simulations. It can talk to multiple clients and
process their requests sequentially.

### Router-worker setup
The Router-worker setup is a more advanced setup that allows load balancing of requests between multiple workers. A
separate router instance is used to distribute requests to multiple workers. Many workers can be spun up to take over
multiple GPUs.

### Installation
If you have a python interpreter that runs chroma, this package will work. The router program is minimal and can run
with very minimal dependencies (just pyzmq).

### Current protocol
Currently, ChAR0N just accepts binary chunks sent in a specific sequence via 0mq's send_multipart or equivalent. In the
future we might move to something more flexible like msgpack. 

All the magic numbers/bytes are stored in `config.py`.

All messages should start with a header chunk. The currently supported headers are:
- `b'PING'`: The client sends a ping to the server. We respond with a 'PONG' message.
- `b'DETECTOR_INFO'`: The client requests information about the detector geometry. Right now the response is set of
  parallel arrays about the PMTs, indexed by the channel_id. Response chunks are:
  | Response Chunks | Data Type                           |
  |-----------------|-------------------------------------|
  | PMT x-position  | float32                             |
  | PMT y-position  | float32                             |
  | PMT z-position  | float32                             |
  | PMT type        | int32                               |
- `b'PHOTONDATA'`: The client sends a chunk of photon data for chroma to simulate. We will respond with a message of the
  simulated photons.
  - Expected incoming chunks:
  
  | Expected Chunks         | Data Type  | Description |
  |-------------------------|------------|-------------|
  | Metadata                | uint32     | A list of `[Event_id, Num_photons]` |
  | x-position       | float32    | Parallel array for each photon |
  | y-position       | float32    | Parallel array for each photon |
  | z-position       | float32    | Parallel array for each photon |
  | x-direction      | float32    | Parallel array for each photon |
  | y-direction      | float32    | Parallel array for each photon |
  | z-direction      | float32    | Parallel array for each photon |
  | x-polarization   | float32    | Parallel array for each photon |
  | y-polarization   | float32    | Parallel array for each photon |
  | z-polarization   | float32    | Parallel array for each photon |
  | wavelength       | float32    | Parallel array for each photon |
  | time             | float32    | Parallel array for each photon |
  | flags            | uint32     | Parallel array for each photon |
  
  - Response chunks:
  
  | Response Chunks         | Data Type  | Description |
  |-------------------------|------------|-------------|
  | Header                  | bytestring | Either `b"SIM_COMPLETE"`, `b"SIM_FAILED"`, or `b"UNKNOWN_REQUEST"` |
  | Metadata                | uint32     | Just the event ID for now   |
  | Hit PMT IDs             | uint32     | Parallel array for each hit |
  | Hit x-direction         | float32    | Parallel array for each hit |
  | Hit y-direction         | float32    | Parallel array for each hit |
  | Hit z-direction         | float32    | Parallel array for each hit |
  | Hit x-polarization      | float32    | Parallel array for each hit |
  | Hit y-polarization      | float32    | Parallel array for each hit |
  | Hit z-polarization      | float32    | Parallel array for each hit |
  | Hit wavelengths         | float32    | Parallel array for each hit |
  | Hit times               | float32    | Parallel array for each hit |
  | Hit flags               | uint32     | Parallel array for each hit |

Flag values are the same as in Chroma:
```
NO_HIT           = 0x1 << 0
BULK_ABSORB      = 0x1 << 1
SURFACE_DETECT   = 0x1 << 2
SURFACE_ABSORB   = 0x1 << 3
RAYLEIGH_SCATTER = 0x1 << 4
REFLECT_DIFFUSE  = 0x1 << 5
REFLECT_SPECULAR = 0x1 << 6
SURFACE_REEMIT   = 0x1 << 7
SURFACE_TRANSMIT = 0x1 << 8
BULK_REEMIT      = 0x1 << 9
CHERENKOV        = 0x1 << 10
SCINTILLATION    = 0x1 << 11
NAN_ABORT        = 0x1 << 31
```

### Example Client
An example client implementation is provided in
[ratpac-two](https://github.com/JamesJieranShen/ratpac-two/tree/chroma-zmq). (This is currently a fork since the changes
have not been fully merged back yet.)

### Future work
- Allow multiple events to be simulated in a single simulation call, and have the server response asynchronously.
- Allow direct calls to RatGeoLoader