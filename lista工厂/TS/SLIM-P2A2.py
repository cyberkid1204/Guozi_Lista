#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : LuBowen
# @Number  : 20210509
# @Time      :2022/6/21 9:54
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
import requests

desc = '项目描述'
para_template = {'SLIM-P2A': {'PickUp': 'str', 'DropOff': 'str'}}
operator_list = []
agv_type = [i for i in range(1, 100)]


async def run(self):
    try:
        while True:
            # self.get_location_pallet_and_type:获取目标位置的当前托盘name和托盘类型name
            location_pallet_detail = await self.get_location_pallet_and_type(self.PickUp)
            # location_pallet_name, location_pallet_type = await self.get_location_pallet_and_type(self.PickUp)
            if location_pallet_detail[0][1]:
               break
            await self.update_order_status(f'there has no pallet on location {self.PickUp}')
            await self.ts_delay(1)
        location_pallet_type = location_pallet_detail[0][1]
        # 查询库区内是否存在位置，不存在则阻塞
        unload_location_name = await get_unload_location(self=self, area_name=self.DropOff,
                                                         pallet_type=location_pallet_type)
        task_id = await self.goto_location_load(self.PickUp, True, agv_type, None, None)
        task_id = await self.goto_location_unload(unload_location_name, False, agv_type, None, task_id)
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await self.cancel()
        # cancel逻辑处理必须在此代码之后
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        return 504


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


# 获取存放库位
async def get_unload_location(self, area_name, pallet_type):
    while True:
        location_name, _ = await self.get_put_location_by_rule([area_name], pallet_type)
        if location_name:
            return location_name
        await self.update_order_status(f'there has no location in area {area_name}')
        await self.ts_delay(0.5)
