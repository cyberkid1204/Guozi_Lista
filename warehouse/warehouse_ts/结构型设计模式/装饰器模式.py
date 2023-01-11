# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations
from abc import ABC, abstractmethod


# 机器人接口
class Robot(ABC):
    @abstractmethod
    def sing(self):
        pass

    @abstractmethod
    def speak(self):
        pass


# 装饰器类
class Decorator(ABC):
    def __init__(self, robot: Robot):
        self.robot = robot

    @abstractmethod
    def dance(self):
        pass

    @abstractmethod
    def running(self):
        pass


class RobotOne(Robot):
    def sing(self):
        print("我可以唱歌")

    def speak(self):
        print("我可以说话")


class DecoratorOne(Decorator):
    def __init__(self, robot: Robot):
        if not hasattr(self, "robot"):
            setattr(self, "robot", robot)
        super(DecoratorOne, self).__init__(robot)

    def dance(self):
        print("我可以跳舞")

    def running(self):
        print('我可以跑步')


if __name__ == '__main__':
    robot_1 = RobotOne()
    robot_1.speak()
    robot_1.sing()
    print("拓展一下".center(50, "-"))
    # robot_2 = DecoratorOne(robot_1)
    # robot_2.robot.speak()
    # robot_2.robot.sing()
    # robot_2.dance()
    # robot_2.running()
    robot_2 = DecoratorOne(robot_1)
    robot_2.robot.sing()
