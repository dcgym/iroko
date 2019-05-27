import numpy as np
import subprocess
import os
import sys
import random
import string

import logging
log = logging.getLogger(__name__)

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)


def shmem_to_nparray(shmem_array, dtype):
    from multiprocessing import Array
    if isinstance(shmem_array, type(Array)):
        return np.frombuffer(shmem_array.get_obj(), dtype=dtype)
    else:
        return np.frombuffer(shmem_array, dtype=dtype)


def exec_process(cmd, host=None, out_file=subprocess.STDOUT):
    if host is not None:
        host_pid = host.pid
        mn_cmd = "mnexec -a %d %s" % (host_pid, cmd)
        return exec_process(mn_cmd, out_file=out_file)
    log.debug("Executing %s " % cmd)
    if out_file is subprocess.STDOUT:
        result = subprocess.run(
            cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stdout:
            log.debug("Process output: %s" % result.stdout)
        if result.stderr and result.returncode != 0:
            log.error(result.stderr)
        return
    err = out_file + ".err"
    out = out_file + ".out"
    with open(out, "w+") as f_out, open(err, "w+") as f_err:
        return subprocess.run(cmd.split(), stdout=f_out, stderr=f_err)


def start_process(cmd, host=None, out_file=subprocess.STDOUT):
    if host is not None:
        host_pid = host.pid
        mn_cmd = "mnexec -a %d %s" % (host_pid, cmd)
        return start_process(mn_cmd, out_file=out_file)
    log.debug("Starting %s " % cmd)
    if out_file is subprocess.STDOUT:
        return subprocess.Popen(cmd.split())
    err = out_file + ".err"
    out = out_file + ".out"
    with open(out, "w+") as f_out, open(err, "w+") as f_err:
        return subprocess.Popen(cmd.split(), stdout=f_out, stderr=f_err)


def list_processes(pattern):
    import psutil
    procs = []
    for proc in psutil.process_iter():
        if pattern in proc.name():
            log.debug("Found %s" % proc)
            procs.append(proc)
    return procs


def kill_processes(procs, use_sigkill=False):
    if type(procs) is not list:
        procs = [procs]
    for proc in procs:
        # kill process, 15 is SIGTERM, 9 is SIGKILL
        try:
            os.kill(proc.pid, 15)
            if use_sigkill:
                os.kill(proc.pid, 9)
        except OSError:
            pass


def kill_processes_with_name(pattern, use_sigkill=False):
    procs = list_processes(pattern)
    kill_processes(procs, use_sigkill)


def dump_json(path, name, data):
    import json
    check_dir(path)
    with open(f"{path}/{name}.json", 'w') as fp:
        json.dump(data, fp)


def change_owner(directory):
    import pwd
    import grp
    if "SUDO_USER" in os.environ:
        user = os.environ["SUDO_USER"]
    else:
        user = os.environ["USER"]

    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(user).gr_gid
    for root, folders, files in os.walk(directory):
        for folder in folders:
            os.chown(os.path.join(root, folder), uid, gid)
        for file in files:
            os.chown(os.path.join(root, file), uid, gid)


def generate_id():
    """ Mininet needs unique ids if we want to launch
     multiple topologies at once """
    # Best collision-free technique for the limited amount of characters
    sw_id = "".join(random.choice("".join([random.choice(
        string.ascii_letters + string.digits)
        for ch in range(4)])) for _ in range(4))
    return sw_id


def check_dir(directory):
    # create the folder if it does not exit
    if not directory == "" and not os.path.exists(directory):
        log.info("Folder %s does not exist! Creating..." % directory)
        os.makedirs(directory)
        # preserve the original owner


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
            log.info("Could not import requested environment: %" % e)
            exit(1)
        return BaseEnv(config)


class TopoFactory(object):
    """ Generator class.
     Returns a target subclass based on the provided target option."""
    @staticmethod
    def create(topo_name, options):
        env_name = "dc_gym.topos.topo_" + topo_name
        env_class = "IrokoTopo"
        log.info("Loading topology %s " % env_name)
        try:
            IrokoTopo = import_from(env_name, env_class)
        except ImportError as e:
            log.info("Could not import requested topology: %s" % e)
            exit(1)
        topo = IrokoTopo(options)
        topo.create_topo()
        return topo
