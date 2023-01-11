# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations
from abc import ABC, abstractmethod


# 定义抽象餐类 Command
class Meals(ABC):
    @abstractmethod
    def execute(self):
        pass


# 定义具体类 ConcreteCommand
class Breakfast(Meals):
    def __init__(self, chief):
        self.chief = chief
        self.name = "早餐"

    def execute(self):
        self.chief.exec(self.name)


class Lunch(Meals):
    def __init__(self, chief):
        self.chief = chief
        self.name = "午餐"

    def execute(self):
        self.chief.exec(self.name)


# 定义接收者类 Receiver
class Chief:
    @staticmethod
    def exec(meals):
        print(f'厨师正在做{meals}.')


# 定义调用者类 Invoker
class Waiter:
    def __init__(self, command: Meals):
        self.chief = command

    def execute_command(self):
        self.chief.execute()


class Customer:
    def __init__(self):
        self.waiter = None

    def making_order(self, waiter):
        self.waiter = waiter
        self.waiter.execute_command()


if __name__ == '__main__':
    chief_1 = Chief()
    breakfast = Breakfast(chief_1)
    lunch = Lunch(chief_1)
    # jennifer = Waiter(breakfast)
    # jennifer.execute_command()

    adrian = Customer()
    adrian.making_order(Waiter(lunch))
