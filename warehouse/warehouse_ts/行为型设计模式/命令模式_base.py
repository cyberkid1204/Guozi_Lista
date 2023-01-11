#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author   : NanZhou
# Version  : python 3.9.7
# =============================================
from __future__ import annotations
from abc import ABC, abstractmethod


# 定义抽象类 Command
class Command(ABC):
    @abstractmethod
    def execute(self):
        pass


# 定义具体类 ConcreteCommand
class ConcreteCommand(Command):
    def __init__(self, receiver):
        self.receiver = receiver

    def execute(self):
        self.receiver.action()


# 定义接收者类 Receiver
class Receiver:
    @staticmethod
    def actions():
        print('Receiver is taking action.')


# 定义调用者类 Invoker
class Invoker:
    def __init__(self, command):
        self.command = command

    def execute_command(self):
        self.command.execute()


# 创建接收者对象
receiver_obj = Receiver()

# 创建命令对象
command_obj = ConcreteCommand(receiver_obj)

# 创建调用者对象
invoker = Invoker(command_obj)

# 调用者执行命令
invoker.execute_command()
