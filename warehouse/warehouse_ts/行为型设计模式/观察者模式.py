# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import List


# 发布者抽象
class Publisher(ABC):
    def __init__(self):
        self.state = None

    @abstractmethod
    def attach(self, observer: Subscriber):
        pass

    @abstractmethod
    def detach(self, observer: Subscriber):
        pass

    @abstractmethod
    def notify(self):
        pass


# 具体的发布者
class ConcretePublisher(Publisher):
    state: int = None
    observers: List[Subscriber] = []

    # 将订阅对象添加到列表中
    def attach(self, observer: Subscriber):
        print("Subject: Attached an observer.")
        self.observers.append(observer)

    # 将订阅对象从列表中删除
    def detach(self, observer: Subscriber):
        print("Subject: Detached an observer.")
        self.observers.remove(observer)

    # 订阅者更新信息
    def notify(self):
        print("Subject: Notifying observers...")
        for ele in self.observers:
            ele.refresh(self)

    # 随机生成状态并让订阅者更新，不同的订阅者会有不同的反应
    def some_business_logic(self):
        print("\nSubject: I'm doing something important.")
        self.state = random.randrange(0, 10)

        print(f"Subject: My state has just changed to: {self.state}")
        self.notify()


# 订阅者抽象
class Subscriber(ABC):
    @abstractmethod
    def refresh(self, subject: Publisher):
        pass


# 具体的订阅者A
class ConcreteObserverA(Subscriber):
    def refresh(self, subject: Publisher):
        if subject.state < 3:
            print("ConcreteObserverA: Reacted to the event")


# 具体的订阅者B
class ConcreteObserverB(Subscriber):
    def refresh(self, subject: Publisher):
        if subject.state == 0 or subject.state >= 2:
            print("ConcreteObserverB: Reacted to the event")


if __name__ == '__main__':
    # 实例化一个发布者subject
    publisher = ConcretePublisher()

    # 实例化一个订阅者A,并添加到发布者列表中
    observer_a = ConcreteObserverA()
    publisher.attach(observer_a)

    # 实例化一个订阅者B,并添加到发布者列表中
    observer_b = ConcreteObserverB()
    publisher.attach(observer_b)

    publisher.some_business_logic()
    publisher.some_business_logic()

    publisher.detach(observer_a)
    publisher.some_business_logic()
