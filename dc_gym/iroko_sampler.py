import os
import multiprocessing
import time
import logging
import shelve
log = logging.getLogger(__name__)

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class StatsSampler(multiprocessing.Process):
    def __init__(self, stats, actions, reward, output_dir):
        multiprocessing.Process.__init__(self)
        self.name = "SampleCollector"
        self.stat_file = f"{output_dir}/statistics.npy"
        self.stats = stats
        self.actions = actions
        self.reward = reward
        self.stat_shelve = None
        self._set_data_checkpoints()
        self.kill = multiprocessing.Event()

    def run(self):
        while not self.kill.is_set():
            try:
                self._checkpoint()
            except KeyboardInterrupt:
                log.error("%s: Caught Interrupt! Exiting...", self.name)
                self.kill.set()
            time.sleep(0.1)
        self._clean()

    def _set_data_checkpoints(self):
        if self.stat_shelve:
            return
        # define file name
        self.stat_shelve = {}
        self.stat_shelve = shelve.open(self.stat_file, 'c', writeback=True)
        self.stat_shelve["reward"] = []
        self.stat_shelve["actions"] = []
        self.stat_shelve["stats"] = []
        self.stat_shelve["num_samples"] = 0

    def stop(self):
        log.info("%s: Received termination signal! Exiting..", self.name)
        self.kill.set()

    def close(self):
        self.stop()
        self.stat_shelve.close()

    def _clean(self):
        if self.stat_shelve:
            try:
                self._flush()
            except Exception as e:
                log.error("Error flushing file %s:\n%s", self.stat_file, e)
            self.stat_shelve = None

    def _checkpoint(self):
        # Save collected data
        self.stat_shelve["stats"].append(self.stats.copy())
        self.stat_shelve["reward"].append(self.reward.value)
        self.stat_shelve["actions"].append(self.actions.copy())
        self.stat_shelve["num_samples"] += 1

    def _flush(self):
        if self.stat_shelve:
            log.info("Writing collected data to disk")
            self.stat_shelve.sync()
            log.info("Done saving statistics...")
