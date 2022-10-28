#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : LuBowen
# @Number  : 20210509
# @FileName  :p2a_lista_new.py
# @Time      :2021/11/17 13:03
# @Software: PyCharm Community Edition
# @Version : Python3
# ====================================
from ts_template.ts_template import CancelException
from ts_template.ts_template import StopException
import sys
import random
import asyncio
import pdb
from pathlib import Path
from datetime import datetime
import time
import json

desc = '项目描述'
para_template = {'p2a_lista_new': {'src': 'str', 'dst_area': 'str', 'pallet_type': 'int'}}
operator_list = []
global_location_locked = []


async def run(self):
    try:
        # 加锁保证多车联动
        await require_lock_location(self=self, location_name='start_order')
        global_location_locked.append('start_order')
        task_id, agv_id = await self.goto_location_reserve(self.src, True, [4, 8], None, None)
        # 选择存放库位
        location_name = await get_unload_location(self=self, area_name=self.dst_area, pallet_type=self.pallet_type)
        # 在起始点添加托盘
        add_status = await add_pallet_to_location(self=self, location=self.src, pallet_type=self.pallet_type)
        if not add_status:
            return 0
        # 开始搬运
        task_id = await self.goto_location_load(self.src, True, [4, 8], agv_id, task_id)
        await require_release_location(self=self, location_name='start_order')
        task_id = await self.goto_location_unload(location_name, True, [4, 8], agv_id, task_id)
        # 搬运空托回原位置
        # 空托计数
        count = await get_empty_pallet_count(self=self)
        # 获取取空托位
        empty_pallet_location = 'Laser Empty {}'.format(count)
        empty_pallet_location_fetch, empty_pallet_location_put = await self.get_location_opt(empty_pallet_location)
        count = await get_empty_pallet_count(self=self)
        task_id = await self.goto_location_act('Laser Empty {}'.format(count), empty_pallet_location_fetch, True,
                                               [4, 8], agv_id,
                                               task_id)
        task_id = await self.goto_location_act(self.src, 1, False, [4, 8], agv_id, task_id)
        await reset_empty_pallet_count(self=self, count=count)
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await self.cancel()
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        return 504
    finally:
        for location in global_location_locked:
            await require_release_location(self=self, location_name=location)


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


async def add_pallet_to_location(self, location, pallet_type):
    pallet_id = await self.add_pallet('pallet{}'.format(time.time_ns()), pallet_type)
    if pallet_id < 0:  # self.add_pallet (返回pallet_id，-1表示托盘类型不存在，-2添加错误，-3表示数据库错误)
        return False
    await self.set_pallet_status(pallet_id, 1)  # 设置托盘状态
    await self.set_pallet_batch_no(pallet_id, 'pallet_batch{}'.format(time.time_ns()))
    await self.set_pallet_location(pallet_id, location)
    return True


# 获取存放库位
async def get_unload_location(self, area_name, pallet_type):
    while True:
        location_name, _ = await self.get_put_location_by_rule([area_name], pallet_type)
        if location_name:
            return location_name
        await self.ts_delay(5)


async def get_empty_pallet_count(self):
    while True:
        try:
            count = await self.get_gp('empty_pallet_count')
            await self.ts_delay(1)
            if count:
                return int(count)
        except Exception as e:
            try:
                await self.set_gp('empty_pallet_count', '6', 'str')
                await self.ts_delay(1)
            except Exception as e:
                pass


async def reset_empty_pallet_count(self, count):
    try:
        if not (count - 1):
            await self.set_gp('empty_pallet_count', str(6), 'str')
        else:
            await self.set_gp('empty_pallet_count', str(count - 1), 'str')
        await self.ts_delay(1)
    except Exception as e:
        pass


async def require_lock_location(self, location_name, block=True):
    """
    申请锁定库位，锁定不成功会一直阻塞
    :param self: ==self
    :param location_name: 库位名称
    :param block: 锁定库位不成功是否返回, True：不返回，False:返回
    :return: None
    """
    while True:
        location_lock_order_id = await get_gp(self=self, key_name=location_name)
        if not location_lock_order_id:
            await set_gp(self=self, key_name=location_name, value=self.order.order_id)
            continue
        if str(location_lock_order_id) != str(self.order.order_id):
            if block:
                await set_order_status_and_logger(self=self,
                                                  logger_info=f'目标{location_name}已经被订单{location_lock_order_id}锁定,本订单将持续申请锁定该库位!')
            else:
                await set_order_status_and_logger(self=self, logger_info='active')
                return False
        else:
            await set_order_status_and_logger(self=self, logger_info=f'成功锁定目标{location_name}')
            return True
        await self.ts_delay(0.5)


async def require_release_location(self, location_name):
    """
    申请释放被锁定的库位
    :param self: ==self
    :param location_name: 库位名称 
    :return: None
    """
    while True:
        location_lock_order_id = await get_gp(self=self, key_name=location_name)
        if str(location_lock_order_id) != str(self.order.order_id):
            await set_order_status_and_logger(self=self, logger_info=f'成功释放目标{location_name}')
            return
        else:
            await delete_gp_record(self=self, key_name=location_name, value=self.order.order_id)
        await self.ts_delay(0.5)


# 只将数据插入全局表
async def set_gp(self, key_name, value):
    """
    :param self: ==self
    :param key_name: 设置的键
    :param value: 设置的值
    :return:
    """
    try:
        check_set_sql = f"select gp_id from layer4_1_om.globalparameters where gp_name=\'{key_name}\' limit 1;"
        result = await self.run_sql(check_set_sql)
        insert_or_update_sql = ''
        if not result:
            insert_or_update_sql = f"insert into layer4_1_om.globalparameters(gp_name, gp_value, gp_value_type) values(\'{key_name}\', \'{value}\', \'str\');"
        else:
            insert_or_update_sql = f"update layer4_1_om.globalparameters set gp_value=\'{value}\' where gp_name=\'{key_name}\';"
        await self.run_sql(insert_or_update_sql)
        return True
    except Exception as e:
        await self.log(e)
    return False


# 从全局表查询数据
async def get_gp(self, key_name):
    """
    :param self: ==self
    :param key_name: 查询的键
    :return: 查询的值
    """
    try:
        check_set_sql = f"select gp_value from layer4_1_om.globalparameters where gp_name=\'{key_name}\' limit 1;"
        await self.log(check_set_sql)
        result = await self.run_sql(check_set_sql)
        await self.log(f'check_set_sql_result={result}')
        if result:
            return result[0].get('gp_value')
    except Exception as e:
        await self.log(e)
    return None


async def logger(self, logger_info):
    await self.log(
        f'Order({self.order.order_id}):****************************{logger_info}********************************')


async def set_order_status_and_logger(self, logger_info, block=False, delay=0.5):
    """
    设置订单状态同时写日志
    :param self: ==self
    :param logger_info:写入的订单状态和日志信息
    :param block: 是否阻塞循环,阻塞寻黄状态下持续循环写订单状态和日志不退出,True为陷入阻塞,False为不阻塞.默认False
    :param delay: 循环阻塞间隔时长，默认0.5
    :return: None
    """
    while True:
        await self.update_order_status(logger_info)
        await logger(self=self, logger_info=logger_info)
        if not block:
            return
        await self.ts_delay(delay)


async def delete_gp_record(self, key_name, value):
    sql = f"delete from layer4_1_om.globalparameters where gp_name=\'{key_name}\' and gp_value=\'{value}\';"
    await logger(self=self, logger_info=sql)
    await self.run_sql(sql)
