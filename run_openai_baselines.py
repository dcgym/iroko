import sys
import re
import os.path as osp
import gym
import numpy as np

from baselines.common.cmd_util import common_arg_parser, parse_unknown_args, make_env
from baselines.common.tf_util import get_session
from baselines import logger
from importlib import import_module


def get_default_network(env_type):
    if env_type in {'atari', 'retro'}:
        return 'cnn'
    else:
        return 'mlp'


def train(args, extra_args):

    total_timesteps = 100000  # int(args.num_timesteps)
    seed = args.seed
    print(seed)

    learn = get_learn_function(args.alg)

    env = build_env(args)

    model = learn(
        env=env,
        seed=seed,
        total_timesteps=total_timesteps,
        network="mlp"
    )

    return model, env


def build_env(env_config):

    iterations = 1000
    gym.register(id='dc-iroko-v0',
                 entry_point='dc_gym.env_iroko:DCEnv',
                 max_episode_steps=iterations,
                 )
    env = make_env('dc-iroko-v0', conf={})
    return env


def get_env_type(args):
    env_id = args.env
    print(args.env)
    if args.env_type is not None:
        return args.env_type, env_id

    # Re-parse the gym registry, since we could have new envs since last time.
    for env in gym.envs.registry.all():
        env_type = env._entry_point.split(':')[0].split('.')[-1]

    env_type = None
    if ':' in env_id:
        env_type = re.sub(r':.*', '', env_id)
    assert env_type is not None, 'env_id {} is not recognized in env types'.format(
        env_id)

    return env_type, env_id


def get_alg_module(alg, submodule=None):
    submodule = submodule or alg
    try:
        # first try to import the alg module from baselines
        alg_module = import_module('.'.join(['baselines', alg, submodule]))
    except ImportError:
        # then from rl_algs
        alg_module = import_module('.'.join(['rl_' + 'algs', alg, submodule]))

    return alg_module


def get_learn_function(alg):
    return get_alg_module(alg).learn


def get_learn_function_defaults(alg, env_type):
    try:
        alg_defaults = get_alg_module(alg, 'defaults')
        kwargs = getattr(alg_defaults, env_type)()
    except (ImportError, AttributeError):
        kwargs = {}
    return kwargs


def parse_cmdline_kwargs(args):
    '''
    convert a list of '='-spaced command-line arguments to a dictionary, evaluating python objects when possible
    '''
    def parse(v):

        assert isinstance(v, str)
        try:
            return eval(v)
        except (NameError, SyntaxError):
            return v

    return {k: parse(v) for k, v in parse_unknown_args(args).items()}


def main(args):
    import logging
    # configure logger, disable logging in child MPI processes (with rank > 0)
    logging.basicConfig(format="%(levelname)s:%(message)s",
                        level=logging.INFO)

    arg_parser = common_arg_parser()
    args, unknown_args = arg_parser.parse_known_args(args)
    extra_args = parse_cmdline_kwargs(unknown_args)

    rank = 0

    model, env = train(args, extra_args)

    if args.save_path is not None and rank == 0:
        save_path = osp.expanduser(args.save_path)
        model.save(save_path)

    if args.play:
        logger.log("Running trained model")
        obs = env.reset()

        state = model.initial_state if hasattr(
            model, 'initial_state') else None
        dones = np.zeros((1,))

        episode_rew = 0
        while True:
            if state is not None:
                actions, _, state, _ = model.step(obs, S=state, M=dones)
            else:
                actions, _, _, _ = model.step(obs)

            obs, rew, done, _ = env.step(actions)
            episode_rew += rew
            done = done
            if done:
                print('episode_rew={}'.format(episode_rew))
                episode_rew = 0
                obs = env.reset()

    env.close()

    return model


if __name__ == '__main__':
    main(sys.argv)
