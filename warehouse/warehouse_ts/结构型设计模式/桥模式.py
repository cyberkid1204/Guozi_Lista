# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations

from abc import ABC, abstractmethod


# class Shape(metaclass=ABCMeta):
#     def __init__(self, color):
#         self.color = color
#
#     @abstractmethod
#     def draw(self):
#         pass
#
#
# class Color(metaclass=ABCMeta):
#     @abstractmethod
#     def paint(self, shape):
#         pass
#
#
# class Rectangle(Shape):
#     name = "长方形"
#
#     def draw(self):
#         self.color.paint(self)
#
#
# class Circle(Shape):
#     name = "圆形"
#
#     def draw(self):
#         self.color.paint(self)
#
#
# class Red(Color):
#     def paint(self, shape):
#         print("红色的%s" % shape.name)
#
#
# class Blue(Color):
#     def paint(self, shape):
#         print("蓝色的%s" % shape.name)
#
#
# shape1 = Rectangle(Red())
# shape1.draw()

class Shape(ABC):
    def __init__(self, color: Color) -> None:
        self.color = color

    @abstractmethod
    def draw(self):
        pass


class Color(ABC):
    @abstractmethod
    def paint(self, shape: Shape) -> None:
        pass


class Rectangle(Shape):
    name = "长方形"

    def draw(self):
        self.color.paint(self)


class Circle(Shape):
    name = "圆形"

    def draw(self):
        self.color.paint(self)


class Red(Color):
    def paint(self, shape):
        print("红色的%s" % shape.name)


class Blue(Color):
    def paint(self, shape):
        print("蓝色的%s" % shape.name)


if __name__ == '__main__':
    shape1 = Rectangle(Red())
    shape2 = Rectangle(Blue())
    shape3 = Circle(Red())
    shape4 = Circle(Blue())
    shape1.draw()
    shape2.draw()
    shape3.draw()
    shape4.draw()
