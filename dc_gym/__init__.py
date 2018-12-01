from gym.envs.registration import register

register(
    id='dc-iroko-v0',
    entry_point='dc_gym.env_iroko:DCEnv',
)
register(
    id='dc-tcp-v0',
    entry_point='dc_gym.env_tcp:DCEnv',
)
