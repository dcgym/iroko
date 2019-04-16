import sys
import os
from dc_gym.log import IrokoLogger
log = IrokoLogger("iroko")

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)


def import_from(module, name):
    """ Try to import a module and class directly instead of the typical
        Python method. Allows for dynamic imports. """
    module = __import__(module, fromlist=[name])
    return getattr(module, name)


class EnvFactory(object):
    """ Generator class.
     Returns a target subclass based on the provided target option."""
    @staticmethod
    def create(config):
        env_name = "dc_gym.env_" + config["env"]
        env_class = "DCEnv"

        log.info("Loading environment %s " % env_name)
        try:
            BaseEnv = import_from(env_name, env_class)
        except ImportError as e:
            log.info("Could not import requested environment: ", e)
            exit(1)
        return BaseEnv(config)


class TopoFactory(object):
    """ Generator class.
     Returns a target subclass based on the provided target option."""
    @staticmethod
    def create(topo_name, options):
        env_name = "dc_gym.topos.topo_" + topo_name
        env_class = "TopoConfig"

        log.info("Loading topology %s " % env_name)
        try:
            TopoConfig = import_from(env_name, env_class)
        except ImportError as e:
            log.info("Could not import requested topology: ", e)
            exit(1)
        return TopoConfig(options)
