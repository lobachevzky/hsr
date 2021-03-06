#!/usr/bin/env python
import argparse
import sys

from baselines import bench, logger
from baselines.ppo2.policies import MlpPolicy
from environment.arm2pos import Arm2PosEnv
from environment.navigate import NavigateEnv
from environment.pick_and_place import PickAndPlaceEnv
from toy_environment.gridworld import Gridworld
from toy_environment import room_obstacle_list


def train(env_id, num_timesteps, seed, policy, record_path, restore_path,
          save_path, nenvs):
    from baselines.common import set_global_seeds
    from baselines.common.vec_env.subproc_vec_env import SubprocVecEnv
    from baselines.common.vec_env.vec_frame_stack import VecFrameStack
    from baselines.ppo2 import ppo2
    from baselines.ppo2.policies import CnnPolicy, LstmPolicy, LnLstmPolicy
    import gym
    import logging
    import multiprocessing
    import os.path as osp
    import tensorflow as tf
    ncpu = multiprocessing.cpu_count()
    if sys.platform == 'darwin':
        ncpu //= 2
    config = tf.ConfigProto(allow_soft_placement=True,
                            intra_op_parallelism_threads=ncpu,
                            inter_op_parallelism_threads=ncpu)
    config.gpu_options.allow_growth = True  # pylint: disable=E1101
    gym.logger.setLevel(logging.WARN)
    tf.Session(config=config).__enter__()

    def make_env(rank):
        def env_fn():
            if env_id == 'toy':
                env = Gridworld(room_obstacle_list.obstacle_list,
                                step_size=0.2, visualize=False)
            elif env_id == 'arm2pos':
                env = Arm2PosEnv(continuous=True, max_steps=500)
            elif env_id == 'pick-and-place':
                env = PickAndPlaceEnv(max_steps=500, neg_reward=False)
            elif env_id == 'navigate':
                env = NavigateEnv(continuous=True, max_steps=500, geofence=.5)
            else:
                env = gym.make(env_id)
            env.seed(seed + rank)
            if record_path:
                logger.warn('`record` is enabled. Program will not log summary/tensorboard values.')
                return gym.wrappers.Monitor(env, record_path)
            else:
                return bench.Monitor(env, logger.get_dir() and osp.join(logger.get_dir(), str(rank)))

        return env_fn

    env = SubprocVecEnv([make_env(i) for i in range(nenvs)])
    set_global_seeds(seed)
    env = VecFrameStack(env, 4)
    policy = {'cnn': CnnPolicy, 'lstm': LstmPolicy, 'lnlstm': LnLstmPolicy, 'mlp': MlpPolicy}[policy]
    ppo2.learn(policy=policy, env=env, nsteps=2048, nminibatches=32,
               lam=0.95, gamma=0.99, noptepochs=10, log_interval=1,
               ent_coef=0.0,
               lr=3e-4, save_interval=30,
               save_path=save_path, restore_path=restore_path,
               cliprange=0.2,
               total_timesteps=num_timesteps)
    # ppo2.learn(policy=policy, env=env, nsteps=128, nminibatches=4,
    #            lam=0.95, gamma=0.99, noptepochs=4, log_interval=1,
    #            ent_coef=.01, save_interval=30,
    #            lr=lambda f: f * 2.5e-4,
    #            cliprange=lambda f: f * 0.1,
    #            total_timesteps=int(num_timesteps * 1.1),
    #            restore_path=restore_path, save_path=save_path)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--env', help='environment ID', default='BreakoutNoFrameskip-v4')
    parser.add_argument('--seed', help='RNG seed', type=int, default=0)
    parser.add_argument('--policy', help='Policy architecture', choices=['cnn', 'lstm', 'lnlstm'], default='mlp')
    parser.add_argument('--num-timesteps', type=int, default=int(10e7))
    parser.add_argument('--num-envs', type=int, default=8)
    parser.add_argument('--tb-dir', default=None)
    parser.add_argument('--output', nargs='+', default=['tensorboard', 'stdout'])
    parser.add_argument('--record-path', default=None)
    parser.add_argument('--restore-path', default=None)
    parser.add_argument('--save-path', default=None)
    args = parser.parse_args()
    logger.configure(dir=args.tb_dir, format_strs=args.output)
    train(args.env, num_timesteps=args.num_timesteps, seed=args.seed,
          policy=args.policy, record_path=args.record_path,
          restore_path=args.restore_path,
          save_path=args.save_path, nenvs=args.num_envs)


if __name__ == '__main__':
    main()
