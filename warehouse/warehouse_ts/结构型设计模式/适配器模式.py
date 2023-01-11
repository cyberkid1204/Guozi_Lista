# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from typing import Union, Optional


# 适配器
class DrinkAdapter:
    @staticmethod
    def drink_adapt(name, size, sweet):
        if name == "咖啡":
            return Coffee(sweet, size, name=name)
        elif name == "奶茶":
            return MilkTea(sweet, size, name=name)
        else:
            print("别瞎搞！")


class Orange:
    def __init__(self, weight: Union[float, int], **kwargs):
        self.fruit_name = "Orange"
        self.price = 6
        self.weight = weight
        self.drink_params = kwargs

    def buy_orange(self):
        total_price = self.weight * self.price
        print("-*-" * 20)
        print("◈您购买的水果：%s\n单价：%s(千克/元)\n重量：%s千克\n需支付金额：%.2f元" % (
            self.fruit_name, self.price, self.weight, total_price))
        return total_price

    def buy_drink(self):
        drink_object = DrinkAdapter.drink_adapt(self.drink_params['name'], self.drink_params['size'], self.drink_params['sweet'])
        return drink_object

    def show(self):
        fruit_price = self.buy_orange()
        if self.drink_params['flag'].capitalize() == "Y":
            drink_money = self.buy_drink().get_price()
        else:
            drink_money = 0
        print("共计：%.2f元" % float(fruit_price + drink_money))


# 饮品类
class Drink:
    def __init__(self, sweet: Optional[int] = None, size: Optional[int] = None, name: Optional[str] = None) -> None:
        self.name = name
        self.sweet = sweet
        self.size = size
        if size == 0:
            self.price = 8.8
        elif size == 1:
            self.price = 12.8
        else:
            self.price = 15.8

    def get_price(self):
        return self.price

    def showinfo(self):
        if self.size == 0:
            size = "小杯"
        elif self.size == 1:
            size = "中杯"
        else:
            size = "大杯"
        print("◎您购买的饮品：%s\n型号：%s\n甜度：%s分糖\n需支付的金额：%.2f元" %
              (self.name, size, self.sweet, self.price))
        print("-*-" * 7)


class MilkTea(Drink):
    tmp = "s"

    def __init__(self, sweet, size, name: Optional[str] = None):
        super(MilkTea, self).__init__(sweet, size, name)
        if not hasattr(self, "name"):
            setattr(self, "name", "Milk-tea")

        self.showinfo()

    @classmethod
    def foo(cls):
        print(cls.__name__)

    def xoo(self):
        print(self.name)


class Coffee(Drink):
    def __init__(self, sweet, size, name: Optional[str] = None):
        super().__init__(sweet, size, name)
        if not hasattr(self, "name"):
            setattr(self, "name", "Coffee")

        self.showinfo()


# 消费者类
class Consumer:

    def __init__(self):
        self._req = dict()
        self.weight = input("请输入要购买的重量（kg)：\n")
        self.flag = input("是否需要购买饮品（y/n)：\n")
        if self.flag.capitalize() == "Y":
            self.drink_name = input("请问选择哪种饮品？\n咖啡/奶茶\n")
            self.drink_size = input("请问选择哪种大小的杯子？\n0：小，1：中，2：大\n")
            self.drink_sweet = input("请输入该饮品的甜度(0~10)\n")
        else:
            self.drink_name = None
            self.drink_size = 0
            self.drink_sweet = 0

    def request(self):
        self._req.update(self.__dict__)


if __name__ == '__main__':
    # customer = Consumer()
    # customer.request()
    # items = Orange(int(customer.weight), name=customer.drink_name, size=customer.drink_size, sweet=customer.drink_sweet,
    #                flag=customer.flag)
    # items.show()
    MilkTea.foo()
    obj = MilkTea(5, 1, "奶茶")
    obj.foo()
