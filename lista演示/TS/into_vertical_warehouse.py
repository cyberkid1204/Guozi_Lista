#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : LuBowen
# @Number  : 20210509
# @FileName  :into_vertical_warehouse_test.py
# @Time      :2022/2/11 9:51
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

desc = '垂直货柜入库'
# task={'task':[{src:location1, pallet_type:5},...]}
para_template = {'into_vertical_warehouse': {'tasks': 'str'}}
operator_list = []
picking_agv_type = [1]

# modula link server config
ip = '127.0.0.1'
port = 5002

# 垂直货柜内库位检查点配置
vertical_location_check_point_mapping = {
    '1001': 'check7',
    '1002': 'check7',
    '1003': 'check7',
}


# 自动货柜内部库位命名规则为：machineID-tray-position

async def run(self):
    try:
        tasks = json.loads(self.tasks)
        await logger(self=self, logger_info=f'tasks={tasks}')
        task_list = tasks.get('task')
        await logger(self=self, logger_info=f'task_list={task_list}')
        src = task_list[0].get('src')
        task_id, agv_id = await self.goto_location_reserve(src, True, picking_agv_type, None, None)
        task_list, task_id = await picking_load(self=self, task_list=task_list, agv_id=agv_id, task_id=task_id)
        await picking_unload(self=self, task_list=task_list, agv_id=agv_id, task_id=task_id)
        await require_release_location(self=self, location_name='vertical_permission')
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


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


async def picking_load(self, task_list, agv_id, task_id=None):
    picking_agv_layer = 1
    for task in task_list:
        picking_src = task.get('src')
        picking_agv_id = agv_id
        task_id = await self.goto_location_load(picking_src, True, picking_agv_type, picking_agv_id, task_id,
                                                picking_agv_layer, None, False)
        task['layer'] = picking_agv_layer
        picking_agv_layer += 1
    return task_list, task_id


async def picking_unload(self, task_list, agv_id, task_id=None):
    current_tray = None
    current_position = None
    has_navigation = True
    while True:
        for task in task_list:
            pallet_type = task.get('pallet_type')
            layer = task.get('layer')
            has_end = task.get('has_end')
            if not has_end:
                location_name, pallet_name = await self.get_put_location_by_rule(['area_vertical'], int(pallet_type))
                if not location_name:
                    await self.update_order_status(
                        f'vertical area has no position to restore goods on picking agv layer {layer}')
                    continue
                else:
                    await self.update_order_status('active')
                    vertical_location_para = location_name.split('-')
                    machineID = vertical_location_para[0]
                    tray = vertical_location_para[1]
                    position = vertical_location_para[-1]
                    check_point = vertical_location_check_point_mapping.get(position)
                    # task_id = await self.goto_location_act(check_point, -1, True, picking_agv_type, agv_id, task_id)
                    await require_lock_location(self=self, location_name='vertical_permission')
                    # call_tray
                    if not current_tray:
                        while True:
                            tray_ready = await call_tray(self=self, machine_id=machineID, tray_no=tray, position=position)
                            if tray_ready:
                                break
                            await self.ts_delay(1)
                    elif current_tray != tray:
                        while True:
                            return_tray_ready = await return_tray(self=self, machine_id=machineID, tray_no=current_tray,
                                                                  position=current_position)
                            if return_tray_ready:
                                break
                            await self.ts_delay(1)
                        await self.ts_delay(15)
                        while True:
                            tray_ready = await call_tray(self=self, machine_id=machineID, tray_no=tray, position=position)
                            if tray_ready:
                                break
                            await self.ts_delay(1)
                    if not has_navigation:
                        task_id = await self.goto_location_act(check_point, -1, True, picking_agv_type, agv_id, task_id)
                        has_navigation = True
                    while True:
                        check_status = await check_command_status(self=self, machine_id=machineID, tray_no=tray,
                                                                  position=position)
                        if check_status:
                            current_tray = tray
                            current_position = position
                            break
                    task_id = await self.goto_location_unload(location_name, True, picking_agv_type,
                                                              agv_id, task_id, layer, None, False)
                    await add_pallet_to_location(self=self, pallet_name=datetime.now().strftime('%Y%m%d%H%M%S%f'),
                                                 batch_no=datetime.now().strftime('%Y%m%d%H%M%S%f'),
                                                 pallet_type=pallet_type,
                                                 location_name=location_name)
                    await self.release_location(location_name)
                    task['has_end'] = True
                    # return tray
        if current_tray:
            while True:
                return_tray_ready = await return_tray(self=self, machine_id=machineID, tray_no=current_tray,
                                                      position=current_position)
                if return_tray_ready:
                    break
                await self.ts_delay(1)
        task_end = check_task_end(task_list)
        if task_end:
            return task_list, task_id


def check_task_end(task_list):
    for task in task_list:
        has_end = task.get('has_end')
        if not has_end:
            return False
    return True


async def call_tray(self, machine_id, tray_no, position, block=True):
    while True:
        try:
            res = requests.post(url=f'http://{ip}:{port}/call_tray/{machine_id}/{tray_no}/{position}', timeout=120)
            await logger(self=self, logger_info=res.text)
            res = json.loads(res.text)
            if res.get('code') in [0, '0']:
                return True
            return False
        except Exception as e:
            await logger(self=self, logger_info=e)
        if not block:
            return False
        await self.ts_delay(2)


async def return_tray(self, machine_id, tray_no, position, block=True):
    while True:
        try:
            res = requests.post(url=f'http://{ip}:{port}/return_tray/{machine_id}/{tray_no}/{position}', timeout=120)
            res = json.loads(res.text)
            await logger(self=self, logger_info=res)
            if res.get('code') in [0, '0']:
                return True
            else:
                return False
        except Exception as e:
            await logger(self=self, logger_info=e)
        if not block:
            return False
        await self.ts_delay(2)


async def check_command_status(self, machine_id, tray_no, position, block=True):
    while True:
        try:
            res = requests.post(url=f'http://{ip}:{port}/check_status/{machine_id}/{tray_no}/{position}', timeout=120)
            res = json.loads(res.text)
            await logger(self=self, logger_info=res)
            if res.get('code') in [0, '0']:
                return True
            else:
                return False
        except Exception as e:
            await logger(self=self, logger_info=e)
        if not block:
            return False
        await self.ts_delay(2)


async def report_to_mes(self, url, json_data, blocking=True, debug=False):
    """
    :param self: self=self
    :param url: 路由
    :param json_data: 上报数据json格式
    :param blocking: 是否阻塞，默认请求阻塞（True），即请求不成功会一直请求
    :param debug: 是否处于调试模式，调试模式下不上报
    :return: None
    """
    if debug:
        return
    headers = {'Content-Type': 'application/json'}
    while True:
        try:
            res = requests.post(url=url, headers=headers, data=json_data, timeout=5)
            res_dict = json.loads(res.text)
            self.logger.info('res_text={}'.format(res.text))
            if res_dict.get('code') in [0, '0']:
                break
        except Exception as e:
            self.logger.error(e)
        if not blocking:
            break
        await self.ts_delay(2)


# 校验库位是否存在
async def check_location(self, location_name):
    """
    :param self: ==self
    :param location_name: 库位名称
    :return: 
    """
    return_location_name = None
    try:
        check_sql = '''select id from layer2_pallet.location where location_name=\'{}\' limit 1;'''.format(
            location_name)
        result = await self.run_sql(check_sql)
        if not result:
            await self.update_order_status('库位{}不存在,本订单将在2min后自动结束!'.format(self.src))
            await self.ts_delay(120)
        else:
            return_location_name = location_name
    except Exception as e:
        await self.update_order_status('库位{}不存在,本订单将在2min后自动结束!'.format(self.src))
        await self.ts_delay(120)
    await self.update_order_status('active')
    return return_location_name


async def lock_location(self, location_name, lock):
    """
    :param self: ==self
    :param location_name: 库位名称
    :param lock: 锁
    :return: 
    """
    lock_start_time = time.time()
    while True:
        try:
            location_lock_status = await get_gp(self=self, key_name=location_name)
            await self.log('lock={}, location_lock_status={}'.format(lock, location_lock_status))
        except Exception as e:
            await set_gp(self=self, key_name=location_name, value='none')
            continue
        if location_lock_status == lock:
            await self.update_order_status('active')
            break
        if location_lock_status == 'none':
            await set_gp(self=self, key_name=location_name, value=lock)
        lock_end_time = time.time()
        lock_spend_time = lock_end_time - lock_start_time
        if lock_spend_time > 20:
            await self.update_order_status(f'库位{location_name}锁定已超时{lock_spend_time - 20}s')
        await self.ts_delay(2)


async def release_location(self, location_name, lock):
    """
    :param self: ==self
    :param location_name: 库位名称
    :param lock: 锁
    :return: 
    """
    release_start_time = time.time()
    while True:
        try:
            location_lock_status = await get_gp(self=self, key_name=location_name)
        except Exception as e:
            await set_gp(self=self, key_name=location_name, value='none')
        if location_lock_status != lock:
            await self.update_order_status('active')
            break
        else:
            await set_gp(self=self, key_name=location_name, value='none')
        release_end_time = time.time()
        release_spend_time = release_end_time - release_start_time
        if release_spend_time > 3:
            await self.update_order_status(f'库位{location_name}解锁已超时{release_spend_time - 3}s')
        await self.ts_delay(2)


# 校验车上是否有货
async def check_goods_in_agv(self, agv_id):
    """
    :param self: ==self
    :param agv_id: agv编号
    :return: 
    """
    sql = f'select * from layer2_pallet.object_location where current_location_id in (select id from layer2_pallet.location where location_name=\'RV{agv_id}-1\') limit 1;'
    while True:
        result = await self.run_sql(sql)
        if not result:
            await self.update_order_status('active')
            return
        else:
            await self.update_order_status(f'第{agv_id}号agv身上有货，无法前往取货，请先移除该agv身上的货物!')
        await self.ts_delay(2)


# 只将数据插入全局表
async def set_gp(self, key_name, value):
    """
    :param self: ==self
    :param key_name: 设置的键
    :param value: 设置的值
    :return: 
    """
    try:
        check_set_sql = f"select gp_id from layer4_1_om.globalparameters where gp_name=\'{key_name}\';"
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
        check_set_sql = f"select gp_value from layer4_1_om.globalparameters where gp_name=\'{key_name}\';"
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


async def add_pallet_to_location(self, pallet_type, batch_no, pallet_name, location_name):
    while True:
        pallet_id = await self.add_pallet(pallet_name, pallet_type)
        if pallet_id < 0:
            await self.update_order_status(f'添加托盘失败, pallet_id={pallet_id}')
        else:
            await self.update_order_status(f'active')
            break
    await self.set_pallet_batch_no(pallet_name, batch_no)
    await self.set_pallet_status(pallet_name, 1)
    while True:
        r = await self.set_pallet_location(pallet_id, location_name)
        if not r:
            await self.update_order_status(f'active')
            return
        await self.update_order_status(f'添加托盘失败, r={pallet_id}')


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


async def delete_gp_record(self, key_name, value):
    sql = f"delete from layer4_1_om.globalparameters where gp_name=\'{key_name}\' and gp_value=\'{value}\';"
    await logger(self=self, logger_info=sql)
    await self.run_sql(sql)


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
