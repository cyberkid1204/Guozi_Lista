# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations
from abc import ABC, abstractmethod


class Duck(ABC):
    def __init__(self, fly_behavior):
        self.fly_behavior = fly_behavior

    def quack(self):
        pass

    def swim(self):
        pass

    @abstractmethod
    def display(self):
        pass


class GreenDuck(Duck):
    def display(self):
        print("我是绿鸭子" + self.fly_behavior.fly())


class RedDuck(Duck):
    def display(self):
        print("我是红鸭子" + self.fly_behavior.fly())


class YellowDuck(Duck):
    def display(self):
        print("我是小黄鸭" + self.fly_behavior.fly())


class ToyDuck(Duck):
    def display(self):
        print("我是玩具鸭" + self.fly_behavior.fly())


class FlyBehavior(ABC):
    @abstractmethod
    def fly(self):
        pass


class FlyWithWings(FlyBehavior):
    @classmethod
    def fly(cls):
        return "，我可以用翅膀飞"


class FlyNoWay(FlyBehavior):
    @classmethod
    def fly(cls):
        return "，我不能飞"


class FlyWithTools(FlyBehavior):
    @classmethod
    def fly(cls):
        return "，我能用竹蜻蜓飞"


if __name__ == '__main__':
    GreenDuck(FlyWithWings).display()
    YellowDuck(FlyNoWay).display()
    ToyDuck(FlyWithTools).display()
