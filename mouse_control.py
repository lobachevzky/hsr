#! /usr/bin/env python3
"""Agent that executes random actions"""
# import gym
import argparse

import numpy as np
from mujoco import ObjType

from environment.arm2pos import Arm2PosEnv

saved_pos = None


def run(port, value_tensor=None, sess=None):
    # env = NavigateEnv(continuous_actions=True, steps_per_action=100, geofence=.3,
    #                   use_camera=False, action_multiplier=.1, image_dimensions=image_dimensions[:2])

    # env = PickAndPlaceEnv(max_steps=9999999, neg_reward=True, use_camera=False, action_multiplier=.01)
    env = Arm2PosEnv(continuous=True, max_steps=9999999, neg_reward=True, use_camera=False, action_multiplier=.01)

    shape, = env.action_space.shape
    i = 0
    action = np.zeros(shape)
    moving = False

    while True:
        lastkey = env.sim.get_last_key_press()
        if moving:
            action[i] += env.sim.get_mouse_dy()
        else:
            for name in ['slide_x_motor', 'slide_y_motor', 'turn_motor']:
                k = env.sim.name2id(ObjType.ACTUATOR, name)
                action[k] = 0
        if lastkey is ' ':
            moving = not moving
            print('\rmoving:', moving)

        for k in range(10):
            if lastkey == str(k):
                i = k - 1
                print('')
                print(env.sim.id2name(ObjType.ACTUATOR, i))

        obs, r, done, _ = env.step(action)
        env.render()

        if done:
            env.reset()
            print('\nresetting')

        assert not env._currently_failed()
        assert_equal(env._goal, env._destructure_goal(env._vector_goal()))
        assert_equal(env._obs(), env._destructure_obs(env._vector_obs()))
        assert_equal(env._gripper_pos(), env._gripper_pos(env.sim.qpos), atol=1e-2)


def assert_equal(val1, val2, atol=1e-5):
    for a, b in zip(val1, val2):
        assert np.allclose(a, b, atol=atol), "{} vs. {}".format(a, b)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=None)
    args = parser.parse_args()

    run(args.port)
