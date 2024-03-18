import chroma
from chroma.loader import create_geometry_from_obj
from chroma.event import Photons
import pickle
import numpy as np
from config import *

class ChromaHandler:
    def __init__ (self, geometry_pickle_path):
        # TODO: directly call RatGeoLoader
        with open(geometry_pickle_path, 'rb') as f:
            self.detector = pickle.load(f)
        self.geo = create_geometry_from_obj(self.detector)
        self.sim = chroma.Simulation(self.geo,
                                     particle_tracking=False,
                                     photon_tracking=False,
                                     geant4_processes=0)
        
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
            t=time
        )
        assert len(photons) == num_photons, "Number of photons does not match metadata"
        return photons, event_id
    
    def run_simulation(self, photons: Photons):
        try:
            event_itr = self.sim.simulate(photons, photons_per_batch=1_000_000,
                              keep_photons_beg=False,
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
        photoelectrons = event.flat_hits
        channel_ids = photoelectrons.channel
        times = photoelectrons.t
        wavelengths = photoelectrons.wavelengths
        return [channel_ids.tobytes(), times.tobytes(), wavelengths.tobytes()]
    
    def process_detector_info(self):
        pmt_positions = np.asarray(self.detector.channel_index_to_position, dtype=np.dtype('f4'))
        pmt_types = np.asarray(self.detector.channel_index_to_channel_type, dtype=np.dtype('i4'))
        return [pmt_positions[:, 0].tobytes(),
                pmt_positions[:, 1].tobytes(),
                pmt_positions[:, 2].tobytes(), 
                pmt_types.tobytes()]

    def respond_to_zmq_request(self, frames: list):
        client_address = frames[0]
        # frames[1] is the delimiter
        messages = frames[2:]
        header = messages[0]
        if header == DETECTOR_INFO:
            detector_info = self.process_detector_info()
            return [client_address, DELIMITER, DETECTOR_INFO] + detector_info
        if header == PHOTONDATA:
            photons, event_id = self.parse_zmq_sim_request(messages)
            event = self.run_simulation(photons)
            if event is None:
                return [client_address, DELIMITER, SIM_FAILED, event_id]
            else:
                processed_event = self.process_event(event)
                return [client_address, DELIMITER, SIM_COMPLETE, event_id] + processed_event
        return [client_address, DELIMITER, UNKNOWN_REQUEST]