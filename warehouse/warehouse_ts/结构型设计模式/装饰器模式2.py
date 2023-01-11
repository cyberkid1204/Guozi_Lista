# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations
from abc import ABC, abstractmethod


class Beverage(ABC):
    @staticmethod
    def description():
        print("这是一个饮料基类")

    @abstractmethod
    def cost(self):
        pass


class MilkTea(Beverage):
    def cost(self):
        print("奶茶5元")
        return "奶茶", 5

    def __repr__(self):
        return "奶茶"


class FruitTea(Beverage):
    def cost(self):
        print("水果茶4元")
        return "水果茶", 4


class Yogurt(Beverage):
    def cost(self):
        print("酸奶5元")
        return "酸奶", 5


class ToppingDecorator(Beverage):
    def __init__(self, beverage):
        self.beverage = beverage

    @abstractmethod
    def cost(self):
        pass


class Boba(ToppingDecorator):
    # def __init__(self, beverage):
    #     super().__init__(beverage)

    def cost(self):
        spent = self.beverage.cost()[1] + 3
        print(f"+boba,一共{spent}元")
        return "boba", spent


class Budding(ToppingDecorator):
    def cost(self):
        spent = self.beverage.cost()[1] + 4
        print(f"+布丁,一共{spent}元")
        return "budding", spent


class GrassJelly(ToppingDecorator):
    def cost(self):
        spent = self.beverage.cost()[1] + 5
        print(f"+仙草,一共{spent}元")
        return "grassjelly", spent


if __name__ == '__main__':
    milktea = MilkTea()
    # milktea.cost()
    # 加珍珠
    Boba(GrassJelly(Budding(Boba(Budding(GrassJelly(Budding(Boba(milktea)))))))).cost()
