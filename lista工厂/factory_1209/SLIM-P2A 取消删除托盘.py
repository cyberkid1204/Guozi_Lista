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
agv_type = [i for i in range(800, 810)]


async def run(self):
    self.pallet_name = None
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
        location_pallet_name = location_pallet_detail[0][0]
        self.pallet_name = location_pallet_name
        # location_pallet = await self.run_sql(
        #     f"""select id from layer2_pallet."object" o where object_name='{location_pallet_name}';""")
        # location_pallet_id = location_pallet[0]['id']
        # 查询库区内是否存在位置，不存在则阻塞
        unload_location_name = await get_unload_location(self=self, area_name=self.DropOff,
                                                         pallet_type=location_pallet_type)
        task_id = await self.goto_location_load(self.PickUp, True, agv_type, None, None)
        task_id = await self.goto_location_unload(unload_location_name, False, agv_type, None, task_id)
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await cancel(self)
        # cancel閫昏緫澶勭悊蹇呴』鍦ㄦ浠ｇ爜涔嬪悗
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        result = await self.run_sql(
            f"""select agv_list[1] from layer4_1_om."order" o where order_id={self.order.order_id};""")
        vehicle_location = f"""RV{result[0].get("agv_list")}-1"""
        lo_id = await self.run_sql(
            f"""select id from layer2_pallet."location" l where location_name = '{vehicle_location}';""")
        vehicle_pallet = await self.get_location_pallet(lo_id[0].get('id'))
        await self.del_pallet(vehicle_pallet)
        return 504


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    await self.del_pallet(self.pallet_name)
    await self.ts_delay(1)
    await check_delete_result(self)
    await self.cancel_task()
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return 1


# 获取存放库位
async def get_unload_location(self, area_name, pallet_type):
    while True:
        location_name, _ = await self.get_put_location_by_rule([area_name], pallet_type)
        if location_name:
            return location_name
        await self.update_order_status(f'there has no location in area {area_name}')
        await self.ts_delay(5)


async def check_delete_result(self):
    try:
        result = await self.run_sql(
            f'select id,object_name from layer2_pallet."object" o where object_name=\'{self.pallet_name}\';')
        if not result:
            self.logger.info(f'##########托盘删除成功##########：{self.pallet_name}')
            return
    except Exception as e:
        self.logger.info(f'##########托盘删除失败##########：{str(e)}')
