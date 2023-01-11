# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations

import time
from typing import List
from abc import ABCMeta, abstractmethod


class Customer(metaclass=ABCMeta):
    def __init__(self, menu: Menu) -> None:
        self.menu = menu

    def ordering(self) -> Menu:
        self.menu = Menu(1, ["兰州炒饭"])
        return self.menu


# 菜单
class Menu:
    def __init__(self, table_id, meals: List[str]) -> None:
        self.id = table_id
        self.meals = meals[0]

    def show(self) -> str:
        return f"桌号：{self.id},餐品：{self.meals}"


# 服务员（Invoker）
class Waiters:
    def __init__(self, customer: Customer, command):
        self.customer = customer
        self.menu = customer.menu
        self.command = command

    def set_command(self) -> None:
        self.command.cooker.add_order()

    def execute_command(self) -> None:
        self.command.execute()


class Command(metaclass=ABCMeta):
    @abstractmethod
    def execute(self, *args):
        pass


class FiredRice(Command):
    def __init__(self, cooker_1) -> None:
        self.cooker = cooker_1

    def execute(self) -> None:
        self.cooker.cook()


class Mike:
    def __init__(self, dishes: Menu):
        self.wait_cook = []
        self.menu = dishes

    def add_order(self):
        self.wait_cook.append(self.menu)

    def remove_order(self, dish):
        self.wait_cook.remove(dish)

    def cook(self):
        for ele in self.wait_cook:
            print(f"开始制作:{ele.meals}")
            print(f"当前单号：{ele.id},前方还有：{len(self.wait_cook) - 1}单")
            # time.sleep(4)
            print("制作中", end="")
            for i in range(6):
                print(".", end='', flush=True)
                time.sleep(0.6)
            print(f"\n制作完成：{ele.meals}")
            self.remove_order(ele)


if __name__ == '__main__':
    Adrian = Customer(Menu(1, ["兰州炒饭"]))
    jennifer = Waiters(Adrian, FiredRice(Mike(Adrian.menu)))
    jennifer.set_command()
    jennifer.execute_command()
