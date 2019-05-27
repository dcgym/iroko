import os
import numpy as np
import multiprocessing
import time
import logging
log = logging.getLogger(__name__)

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class StatsSampler(multiprocessing.Process):

    def __init__(self, stats, actions, reward, output_dir):
        multiprocessing.Process.__init__(self)
        self.name = "SampleCollector"
        self.stats_file = "%s/statistics" % output_dir
        self.stats = stats
        self.actions = actions
        self.reward = reward
        self.stats_samples = None
        self._set_data_checkpoints()
        self.kill = multiprocessing.Event()

    def run(self):
        while not self.kill.is_set():
            try:
                self._checkpoint()
            except KeyboardInterrupt:
                log.error("%s: Caught Interrupt! Exiting..." % self.name)
                self.kill.set()
            time.sleep(0.1)
        self._clean()

    def _set_data_checkpoints(self):
        if self.stats_samples:
            return
        # define file name
        self.stats_samples = {}
        self.stats_samples["reward"] = []
        self.stats_samples["actions"] = []
        self.stats_samples["stats"] = []
        self.stats_samples["num_samples"] = 0

    def stop(self):
        log.info("%s: Received termination signal! Exiting.." % self.name)
        self.kill.set()

    def close(self):
        self.stop()

    def _clean(self):
        if self.stats_samples:
            try:
                self._flush()
            except Exception as e:
                log.error("Error flushing file %s" % self.stats_file, e)
            self.stats_samples = None
        pass

    def _checkpoint(self):
        # Save collected data
        self.stats_samples["stats"].append(self.stats.copy())
        self.stats_samples["reward"].append(self.reward.value)
        self.stats_samples["actions"].append(self.actions.copy())
        self.stats_samples["num_samples"] += 1

    def _flush(self):
        if self.stats_samples:
            log.info("Writing collected data to disk")
            np.save(self.stats_file, self.stats_samples)
            log.info("Done saving statistics...")
