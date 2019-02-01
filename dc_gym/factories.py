import sys
import os
cwd = os.getcwd()
lib_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, lib_dir)


DEFAULT_ENV_CONFIG = {
    "input_dir": lib_dir + '/inputs',
    "output_dir": cwd + '/results',
    "topo": "dumbbell",
    "agent": "PPO",
    "transport": "udp",
    "tf_index": 0,
    "env": "iroko"
}


def import_from(module, name):
    """ Try to import a module and class directly instead of the typical
        Python method. Allows for dynamic imports. """
    module = __import__(module, fromlist=[name])
    return getattr(module, name)


class EnvFactory(object):
    """ Generator class.
     Returns a target subclass based on the provided target option."""
    @staticmethod
    def create(config=DEFAULT_ENV_CONFIG):
        env_name = "dc_gym.env_" + config["env"]
        env_class = "DCEnv"

        print("Loading environment %s " % env_name)
        try:
            BaseEnv = import_from(env_name, env_class)
        except ImportError as e:
            print("Problem: ", e)
            exit(1)
        return BaseEnv(config)


class TopoFactory(object):
    """ Generator class.
     Returns a target subclass based on the provided target option."""
    @staticmethod
    def create(options):
        env_name = "dc_gym.topos.topo_" + options["topo_name"]
        env_class = "TopoConfig"

        print("Loading topology %s " % env_name)
        try:
            TopoConfig = import_from(env_name, env_class)
        except ImportError as e:
            print("Problem: ", e)
            exit(1)
        return TopoConfig(options)
