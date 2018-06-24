import argparse
import time
import os
import logging
from baselines import logger, bench
from baselines.common.misc_util import (
    set_global_seeds,
    boolean_flag,
)
import baselines.ddpg.training as training
from baselines.ddpg.models import Actor, Critic, ActorGoalTrunk, CriticGoalTrunk
from baselines.ddpg.models_cnn import ActorCNN, CriticCNN
from baselines.ddpg.memory import Memory
from baselines.ddpg.noise import *
#from environment.arm2pos import Arm2PosEnv
#from environment.pick_and_place import PickAndPlaceEnv
from toy_environment import continuous_gridworld, continuous_gridworld2
import gym
import tensorflow as tf
#from environment.navigate import NavigateEnv
from mpi4py import MPI


def run(env_id, seed, noise_type, layer_norm, evaluation, **kwargs):
    # Configure things.
    rank = MPI.COMM_WORLD.Get_rank()
    if rank != 0:
        logger.set_level(logger.DISABLED)

    use_cnn = kwargs['use_cnn']
    del kwargs['use_cnn']
    use_cnn = False #TODO Find bug
    # for toy env
    noisy_pos = kwargs['use_noisy_pos']
    del kwargs['use_noisy_pos']

    # Create envs.
    if env_id == 'navigate':
        #env = NavigateEnv(use_camera=False, continuous_actions=True, neg_reward=True, max_steps=500)
        pass
    elif env_id == 'toy':
        #env = continuous_gridworld.ContinuousGridworld('', max_steps=1000, obstacle_mode=continuous_gridworld.NO_OBJECTS)
        from toy_environment import room_obstacle_list
        env = continuous_gridworld2.ContinuousGridworld2(room_obstacle_list.obstacle_list, noise_type, max_action_step=0.2, use_cnn=use_cnn)
    elif env_id == 'arm2pos':
        #env = Arm2PosEnv(continuous=True, max_steps=500)
        pass
    elif env_id == 'pick-and-place':
        #env = PickAndPlaceEnv(max_steps=500)
        pass
    elif env_id == 'four-rooms':
        env = continuous_gridworld2.FourRoomExperiment(noise_type, visualize=False, noisy_position=noisy_pos, use_cnn=use_cnn, max_action_step=kwargs['max_action_step'])
        eval_env = continuous_gridworld2.FourRoomExperiment(noise_type, visualize=False, noisy_position=noisy_pos, use_cnn=use_cnn, max_action_step=kwargs['max_action_step'], eval_=True)
    else:
        env = gym.make(env_id)
    env = bench.Monitor(env, logger.get_dir() and os.path.join(logger.get_dir(), str(rank)))
    # env = gym.wrappers.Monitor(env, '/tmp/ddpg/', force=True)
    gym.logger.setLevel(logging.WARN)

    if env_id == 'four-rooms': pass
    elif evaluation and rank == 0:
        eval_env = gym.make(env_id)
        eval_env = bench.Monitor(eval_env, os.path.join(logger.get_dir(), 'gym_eval'))
        env = bench.Monitor(env, None)
    else:
        eval_env = None

    # Parse noise_type
    action_noise = None
    param_noise = None

    nb_actions = env.action_space.shape[-1]
    for current_noise_type in noise_type.split(','):
        dcurrent_noise_type = current_noise_type.strip()
        if current_noise_type == 'none':
            pass
        elif 'adaptive-param' in current_noise_type:
            _, stddev = current_noise_type.split('_')
            param_noise = AdaptiveParamNoiseSpec(initial_stddev=float(stddev), desired_action_stddev=float(stddev))
        elif 'normal' in current_noise_type:
            _, stddev = current_noise_type.split('_')
            action_noise = NormalActionNoise(mu=np.zeros(nb_actions), sigma=float(stddev) * np.ones(nb_actions))
        elif 'ou' in current_noise_type:
            _, stddev = current_noise_type.split('_')
            action_noise = OrnsteinUhlenbeckActionNoise(mu=np.zeros(nb_actions),
                                                        sigma=float(stddev) * np.ones(nb_actions))
        else:
            raise RuntimeError('unknown noise type "{}"'.format(current_noise_type))

    # Configure components.
    memory = Memory(limit=int(1e5), action_shape=env.action_space.shape, observation_shape=env.observation_space.shape)
    print('actions: {} {}\n\n'.format(nb_actions, use_cnn))
    #critic = CriticGoalTrunk(layer_norm=layer_norm)
    #actor = ActorGoalTrunk(nb_actions, layer_norm=layer_norm)
    if not use_cnn:
        critic = Critic(layer_norm=layer_norm)
        actor = Actor(nb_actions, layer_norm=layer_norm)

    else:
        critic = CriticCNN(layer_norm=layer_norm)
        actor = ActorCNN(nb_actions, layer_norm=layer_norm)


    # Seed everything to make things reproducible.
    seed = seed + 1000000 * rank
    logger.info('rank {}: seed={}, logdir={}'.format(rank, seed, logger.get_dir()))
    tf.reset_default_graph()
    set_global_seeds(seed)
    env.seed(seed)
    if eval_env is not None:
        eval_env.seed(seed)

    # Disable logging for rank != 0 to avoid noise.
    if rank == 0:
        start_time = time.time()
    del kwargs['tb_dir']
    # del kwargs['save_path']
    hindsight_mode = kwargs['hindsight_mode']
    del kwargs['hindsight_mode']
    del kwargs['max_action_step']
    training.train(env=env, eval_env=eval_env, param_noise=param_noise,
                   action_noise=action_noise, actor=actor, critic=critic, memory=memory,
                   hindsight_mode=hindsight_mode, **kwargs)
    env.close()
    if eval_env is not None:
        eval_env.close()
    if rank == 0:
        logger.info('total runtime: {}s'.format(time.time() - start_time))


def parse_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--env-id', type=str, default='HalfCheetah-v1')
    boolean_flag(parser, 'render-eval', default=False)
    boolean_flag(parser, 'layer-norm', default=True)
    boolean_flag(parser, 'render', default=False)
    boolean_flag(parser, 'normalize-returns', default=False)
    boolean_flag(parser, 'normalize-observations', default=True)
    parser.add_argument('--seed', help='RNG seed', type=int, default=0)
    parser.add_argument('--critic-l2-reg', type=float, default=1e-2)
    parser.add_argument('--batch-size', type=int, default=64)  # per MPI worker
    parser.add_argument('--actor-lr', type=float, default=1e-4)
    parser.add_argument('--critic-lr', type=float, default=1e-3)
    boolean_flag(parser, 'popart', default=False)
    parser.add_argument('--gamma', type=float, default=0.99)
    parser.add_argument('--reward-scale', type=float, default=1.)
    parser.add_argument('--clip-norm', type=float, default=None)
    parser.add_argument('--nb-epochs', type=int, default=5000)  # with default settings, perform 1M steps total
    parser.add_argument('--nb-epoch-cycles', type=int, default=20)
    parser.add_argument('--nb-train-steps', type=int, default=50)  # per epoch cycle and MPI worker
    parser.add_argument('--nb-eval-steps', type=int, default=100)  # per epoch cycle and MPI worker
    parser.add_argument('--nb-rollout-steps', type=int, default=100)  # per epoch cycle and MPI worker
    parser.add_argument('--noise-type', type=str, default='normal_0.005')  # choices are adaptive-param_xx, ou_xx, normal_xx, none
    parser.add_argument('--tb-dir', type=str, default=None)
    parser.add_argument('--num-timesteps', type=int, default=None)
    parser.add_argument('--restore', type=bool, default=False) # restores latest from save-path
    parser.add_argument('--save-path', type=str, default=None)
    parser.add_argument('--hindsight-mode', type=str, default=None)
    parser.add_argument('--use-cnn', type=bool, default=False)
    parser.add_argument('--use-noisy-pos', type=bool, default=False)
    parser.add_argument('--max-action-step', type=float, default=0.0025)
    boolean_flag(parser, 'evaluation', default=False)
    args = parser.parse_args()
    # we don't directly specify timesteps for this script, so make sure that if we do specify them
    # they agree with the other parameters
    if args.save_path is not None:
        print('Current Save Path: {}'.format(args.save_path))
    if args.num_timesteps is not None:
        assert (args.num_timesteps == args.nb_epochs * args.nb_epoch_cycles * args.nb_rollout_steps)
    dict_args = vars(args)
    del dict_args['num_timesteps']
    return dict_args


if __name__ == '__main__':
    args = parse_args()
    if MPI.COMM_WORLD.Get_rank() == 0:
        logger.configure()
    if args['tb_dir'] is not None:
        logger.configure(dir=args['tb_dir'], format_strs=['stdout', 'tensorboard'])
    # Run actual script.
    run(**args)
