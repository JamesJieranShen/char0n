import chroma
from chroma.loader import create_geometry_from_obj
from chroma.event import Photons
import pickle
import numpy as np
from config import *
from time import perf_counter
from pathlib import Path
import awkward as ak
import uproot


class ChromaHandler:
    def __init__(self, geometry_pickle_path, async_mode=False, outdir=None):
        # TODO: directly call RatGeoLoader
        with open(geometry_pickle_path, 'rb') as f:
            self.detector = pickle.load(f)
        self.geo = create_geometry_from_obj(self.detector)
        self.sim = chroma.Simulation(self.geo,
                                     particle_tracking=False,
                                     photon_tracking=False,
                                     geant4_processes=0)
        self.async_mode = async_mode
        self.outdir = Path(outdir) if outdir is not None else Path('.')
        self.outdir = self.outdir.resolve()
        self.sim_times = []

    def recreate_simulation(self):
        self.event_queue = []
        self.event_itr = self.sim.simulate(self.event_queue, photons_per_batch=2_000_000,
                                            keep_photons_beg=True,
                                            keep_photons_end=True,
                                            keep_hits=False,
                                            keep_flat_hits=True,
                                            run_daq=False)
    
    def setup_run(self, messages: list):
        assert messages[0] == RUN_BEGIN, "First message is not RUN_BEGIN"
        assert len(messages) == 2, f"Unexpected message length of {len(messages)}"
        fname = Path(messages[1].decode('utf-8'))
        # strip extensions
        if not self.async_mode:
            print("BEGIN RUN Received, but server is running in synchronous mode. Do nothing.")
            return
        while fname.suffix in {'.root', '.ntuple'}:
            fname = fname.with_suffix('')
        fname = fname.with_suffix('.charon.ntuple.root')
        fname = self.outdir / fname
        print("Run will be written to ", fname)
        self.event_per_basket = 500
        self.outfile = uproot.recreate(fname)
        self.event_in_buffer = 0
        self.event_buffer = {
            "event_id"      : [],
            "channel_id"    : [],
            "time"          : [],
            "wavelength"    : [],
            "u"             : [],
            "v"             : [],
            "w"             : [],
            "pol_x"         : [],
            "pol_y"         : [],
            "pol_z"         : [],
            "flag"          : [],
        }
        
        pmt_positions = np.asarray(
            self.detector.channel_index_to_position, dtype=np.dtype('f4'))
        pmt_types = np.asarray(
            self.detector.channel_index_to_channel_type, dtype=np.dtype('i4'))
        self.outfile['detinfo'] = {
                                "pmt_x":    pmt_positions[:, 0],
                                "pmt_y":    pmt_positions[:, 1],
                                "pmt_z":    pmt_positions[:, 2],
                                "pmt_type": pmt_types
        }
        self.outfile.mktree("output", {
                                "event_id"      : "uint32",
                                "channel_id"    : "var * uint32",
                                "time"          : "var * float32",
                                "wavelength"    : "var * float32",
                                "u"             : "var * float32",
                                "v"             : "var * float32",
                                "w"             : "var * float32",
                                "pol_x"         : "var * float32",
                                "pol_y"         : "var * float32",
                                "pol_z"         : "var * float32",
                                "flag"          : "var * uint32",
                            })

        self.recreate_simulation()


    def parse_zmq_sim_request(self, messages: list):
        assert messages[0] == PHOTONDATA, "First message frame is not PHOTONDATA"
        assert len(messages) >= N_DATABLOCKS, \
            "Not enough data blocks in message"
        metadata = np.frombuffer(messages[1], dtype=np.dtype('u4'))
        event_id = metadata[0]
        num_photons = metadata[1]

        pos_x = np.frombuffer(messages[2], dtype=np.dtype('f4'))
        pos_y = np.frombuffer(messages[3], dtype=np.dtype('f4'))
        pos_z = np.frombuffer(messages[4], dtype=np.dtype('f4'))
        dir_x = np.frombuffer(messages[5], dtype=np.dtype('f4'))
        dir_y = np.frombuffer(messages[6], dtype=np.dtype('f4'))
        dir_z = np.frombuffer(messages[7], dtype=np.dtype('f4'))
        pol_x = np.frombuffer(messages[8], dtype=np.dtype('f4'))
        pol_y = np.frombuffer(messages[9], dtype=np.dtype('f4'))
        pol_z = np.frombuffer(messages[10], dtype=np.dtype('f4'))
        wavelengths = np.frombuffer(messages[11], dtype=np.dtype('f4'))
        time = np.frombuffer(messages[12], dtype=np.dtype('f4'))
        flags = np.frombuffer(messages[13], dtype=np.dtype('u4'))
        assert len(pos_x) == len(pos_y) == len(pos_z) == len(dir_x) == len(dir_y) == len(dir_z) == len(pol_x) == len(
            pol_y) == len(pol_z) == len(wavelengths) == len(time) == len(flags), "Data arrays are not the same length"

        position = np.asarray([pos_x, pos_y, pos_z]).T
        direction = np.asarray([dir_x, dir_y, dir_z]).T
        polarization = np.asarray([pol_x, pol_y, pol_z]).T
        wavelengths = np.asarray(wavelengths)
        time = np.asarray(time)
        photons = Photons(
            pos=position,
            dir=direction,
            pol=polarization,
            wavelengths=wavelengths,
            t=time,
            flags=flags
        )
        assert len(
            photons) == num_photons, "Number of photons does not match metadata"
        return photons, event_id

    def run_simulation(self, photons: Photons):
        try:
            event_itr = self.sim.simulate(photons, photons_per_batch=2_000_000,
                                          keep_photons_beg=True,
                                          keep_photons_end=True,
                                          keep_hits=False,
                                          keep_flat_hits=True,
                                          run_daq=False)
            events = list(event_itr)
            assert len(events) == 1, "More than one event returned"
            return events[0]
        except Exception as e:
            print(f"Error in simulation: {e}")
            return None

    def process_event(self, event):
        if event is not None:
            photoelectrons = event.flat_hits
        else:
            photoelectrons = Photons()
        
        print("Number of hits: ", len(photoelectrons))
        channel_ids = photoelectrons.channel
        times = photoelectrons.t
        wavelengths = photoelectrons.wavelengths
        dir_x = photoelectrons.dir[:, 0]
        dir_y = photoelectrons.dir[:, 1]
        dir_z = photoelectrons.dir[:, 2]
        pol_x = photoelectrons.pol[:, 0]
        pol_y = photoelectrons.pol[:, 1]
        pol_z = photoelectrons.pol[:, 2]
        flags = photoelectrons.flags
        cher_hits = np.bitwise_and(flags, (0x1 << 10)) != 0
        if self.async_mode:
            self.event_buffer['channel_id'].append(channel_ids)
            self.event_buffer['time'].append(times)
            self.event_buffer['wavelength'].append(wavelengths)
            self.event_buffer['u'].append(dir_x)
            self.event_buffer['v'].append(dir_y)
            self.event_buffer['w'].append(dir_z)
            self.event_buffer['pol_x'].append(pol_x)
            self.event_buffer['pol_y'].append(pol_y)
            self.event_buffer['pol_z'].append(pol_z)
            self.event_buffer['flag'].append(flags)
            
        return [
            channel_ids.tobytes(),
            dir_x.tobytes(), dir_y.tobytes(), dir_z.tobytes(),
            pol_x.tobytes(), pol_y.tobytes(), pol_z.tobytes(),
            wavelengths.tobytes(),
            times.tobytes(),
            flags.tobytes()
        ]

    def process_detector_info(self):
        pmt_positions = np.asarray(
            self.detector.channel_index_to_position, dtype=np.dtype('f4'))
        pmt_types = np.asarray(
            self.detector.channel_index_to_channel_type, dtype=np.dtype('i4'))
        return [pmt_positions[:, 0].tobytes(),
                pmt_positions[:, 1].tobytes(),
                pmt_positions[:, 2].tobytes(),
                pmt_types.tobytes()]
    
    def flush_event_buffer(self):
        start = perf_counter()
        # Fill event buffer by polling the Generator
        for evt in self.event_itr:
            self.process_event(evt)
        basket_to_write = {k: ak.from_iter(v) for k, v in self.event_buffer.items()}
        self.outfile['output'].extend(basket_to_write)
        # Clear buffer
        for key in self.event_buffer:
            self.event_buffer[key] = []
        self.event_in_buffer = 0
        self.recreate_simulation()
        end = perf_counter()
        print("Buffer flushing took", end-start, "seconds")

    def respond_to_zmq_request(self, frames: list):
        # We might be receiving using a router socket or a rep socket.
        # Envelope needs to be added for router.
        if len(frames) < 2 or frames[1] != DELIMITER:
            delimited = False
        else:
            delimited = True
        client_address = frames[0] if delimited else None
        # frames[1] is the delimiter
        messages = frames[2:] if delimited else frames
        header = messages[0]
        response = [client_address, DELIMITER] if delimited else []
        if header == RUN_BEGIN:
            self.setup_run(messages)
            response.append(ACK)
        elif header == DETECTOR_INFO:
            detector_info = self.process_detector_info()
            response.append(DETECTOR_INFO)  # Header
            response.extend(detector_info)  # body
        elif header == PHOTONDATA:
            sim_begin = perf_counter()
            photons, event_id = self.parse_zmq_sim_request(messages)
            if self.async_mode:
                self.event_queue.append(photons)
                response.append(SIM_COMPLETE_ASYNC)
                response.append(event_id)
                print(f"Asynchronous event registered. Event includes {len(photons)} photons")
                self.event_in_buffer += 1
                self.event_buffer['event_id'].append(event_id)
                if self.event_in_buffer >= self.event_per_basket:
                    self.flush_event_buffer()
            else: # Synchronous writeback mode
                event = self.run_simulation(photons)
                sim_end = perf_counter()
                print(
                    f"Simulation took {sim_end - sim_begin:.2f} seconds, there were {len(photons)} photons.")
                self.sim_times.append(sim_end - sim_begin)
                print(f"Sim time running average: {np.mean(self.sim_times)}")
                if event is None:
                    response.append(SIM_FAILED)
                    response.append(event_id)
                else:
                    processed_event = self.process_event(event)
                    response.append(SIM_COMPLETE)
                    response.append(event_id)
                    response.extend(processed_event)
        elif header == RUN_END:
            print("Run End signal received")
            if self.async_mode:
                if self.event_in_buffer != 0:
                    self.flush_event_buffer()
                self.outfile.close()
                print("Finished writing events. File is closed!")
            response.append(ACK)

        else:
            response.append(UNKNOWN_REQUEST)
        print("=========================================================")
        return response
