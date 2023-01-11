#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : LuBowen
# @Number  : 20210509
# @FileName  :test_navigation.py
# @Time      :2022/5/10 16:16
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
para_template = {'test_navigation': {'agv_id': 'int', 'src': 'str', 'dst': 'str'}}
operator_list = []
# ===================================基本配置区==========================================
# 作业车类型列表
agv_type = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
# mes或者wms或者wcs的ip:端口/域名配置
mes_ip_port = '127.0.0.1:1000'
# 调度系统restAPI服务ip及端口配置
rest_api_ip_port = '127.0.0.1:6767'
# 请求头设置
headers = {'Content-Type': 'application/json'}
# 是否开启调试模式，调试模式下，不与mes等进行交互相关操作。False表示不开启调试模式，True表示开启调试模式
debug_mode = False
# 全局库位锁定表
global_location_locked = []
# 库位取货前检查点配置
pre_load_check_point_map = {
    'A-1-1': 'B-1-1',
    'A-2-1': 'B-2-1',
    'A-3-1': 'B-3-1',
}
# 库位取货后检查点配置
after_load_check_point_map = {
    'A-1-1': 'B-4-1',
    'A-2-1': 'B-5-1',
    'A-3-1': 'B-6-1',
}
# 库位卸货前检查点配置
pre_unload_check_point_map = {
    'A-1-1': 'B-1-5',
    'A-2-1': 'B-2-5',
    'A-3-1': 'B-3-5',
}
# 库位卸货后检查点配置, 卸货后的检查点必须在地图上设置在安全区外
after_unload_check_point_map = {
    'A-1-1': 'B-4-5',
    'A-2-1': 'B-5-5',
    'A-3-1': 'B-6-5',
}
# 上报mes路由配置
report_start_url = f'http://{mes_ip_port}/wcs/reportOrderStatus'
report_finish_url = f'http://{mes_ip_port}/wcs/reportOrderStatus'
report_cancel_url = f'http://{mes_ip_port}/wcs/reportOrderStatus'
report_error_url = f'http://{mes_ip_port}/wcs/reportOrderStatus'


# ===================================基本配置区==========================================

async def run(self):
    order_status = 'start'
    error_reason = None
    agv_id = self.agv_id
    src = self.src
    dst = self.dst
    task_id = None
    try:
        task_id = await self.goto_location_act(src, -1, True, agv_type, agv_id, task_id)
        task_id = await self.goto_location_act(dst, -1, True, agv_type, agv_id, task_id)
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await self.cancel()
        # cancel逻辑处理必须在此代码之后
        order_status = 'cancel'
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        error_reason = e.args[0].replace("'", "*")
        order_status = 'error'
        return 504


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


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
                await set_order_status_and_logger(self=self, logger_info=f'上报wcs成功, 响应信息为{res.text}')
                break
            else:
                await set_order_status_and_logger(self=self, logger_info=f'上报wcs成功,但是wcs未通过请求,wcs响应信息为:{res.text}')
        except Exception as e:
            await set_order_status_and_logger(self=self, logger_info='wcs无法访问,请检查wcs服务是否已离线!')
            self.logger.error(e)
        if not blocking:
            break
        await self.ts_delay(0.5)


# 校验库位是否存在
async def check_location(self, location_name):
    """
    :param self: ==self
    :param location_name: 库位名称
    :return: 
    """
    try:
        check_sql = '''select id from layer2_pallet.location where location_name=\'{}\' limit 1;'''.format(
            location_name)
        result = await self.run_sql(check_sql)
        await logger(self=self, logger_info=f'check_location_result={result}')
        if not result:
            return None
        return location_name
    except Exception as e:
        await logger(self=self, logger_info=e)
    return None


# 校验车上是否有货
async def check_goods_in_agv(self, agv_id):
    """
    :param self: ==self
    :param agv_id: agv编号
    :return: 
    """
    sql = f'select * from layer2_pallet.object_location where current_location_id in (select id from layer2_pallet.location where location_name=\'RV{agv_id}-1\' limit 1) limit 1;'
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


async def goto_location_load(self, location_name, follow_task, agv_type, agv_id, pre_task_id, layer=None, p4=None,
                             manage_mode=False, pre_check_point=None, after_check_point=None):
    """
    本omi只针对单层车
    :param self: ==self
    :param location_name: 目的地库位名称
    :param follow_task: 布尔值，是否有后置任务
    :param agv_type: 执行任务的agv类型列表
    :param agv_id: 指定执行任务的agv
    :param pre_task_id: 前置任务id
    :param manage_mode: 是否执行库管，True执行库管逻辑,False不执行库管逻辑
    :param layer: agv指定层
    :param p4: None
    :param pre_check_point:取货前检查点,如果配置了该参数，agv将在取货前先导航到该检查点
    :param after_check_point:取货后检查点，如果配置了该参数，agv将在取货后导航到该检查点
    :return:task_id
    """
    task_id = pre_task_id
    # 判断车身上是否有货
    if agv_id and manage_mode:
        while True:
            agv_pallet_name = await self.get_location_pallet(f'RV{agv_id}-1')
            if not agv_pallet_name:
                break
            else:
                await set_order_status_and_logger(self=self, logger_info=f'第{agv_id}号agv身上有货,请先移除agv身上的托盘!')
            await self.ts_delay(0.5)
    if pre_check_point:
        await set_order_status_and_logger(self=self, logger_info=f'前往取货前检查点{pre_check_point}')
        task_id = await self.goto_location(pre_check_point, -1, True, agv_type, agv_id, task_id)

    # 锁定库位
    await require_lock_location(self=self, location_name=location_name)
    await set_order_status_and_logger(self=self, logger_info=f'成功锁定库位{location_name}')
    if location_name not in global_location_locked:
        global_location_locked.append(location_name)
    # 库位锁定成功之后，如果是带库管模式，则需要在取货前判断库位上是否有货,有货则直接执行搬运任务，无货则释放锁定的库位
    if manage_mode:
        while True:
            pallet_name = await self.get_location_pallet(location_name)
            if pallet_name:
                await set_order_status_and_logger(self=self, logger_info='库位有货, agv将前往取货')
                break
            else:
                await set_order_status_and_logger(self=self,
                                                  logger_info=f'库位{location_name}上无货,无法前往执行取货任务,请先在库位上放置托盘!')
            await self.ts_delay(0.5)
    # 不带库管模式下，锁定库位之后立即执行搬运任务
    if after_check_point:
        task_id = await self.goto_location_load(location_name, True, agv_type, agv_id, task_id, layer, p4,
                                                manage_mode)
        await require_release_location(self=self, location_name=location_name)
        await set_order_status_and_logger(self=self, logger_info=f'取货结束，前往取货后检查点{after_check_point}')
        task_id = await self.goto_location(after_check_point, -1, follow_task, agv_type, agv_id, task_id)
    else:
        task_id = await self.goto_location_load(location_name, follow_task, agv_type, agv_id, task_id, layer, p4,
                                                manage_mode)
        await require_release_location(self=self, location_name=location_name)
    return task_id


async def goto_location_unload(self, location_name, follow_task, agv_type, agv_id, pre_task_id, layer=None, p4=None,
                               manage_mode=False, pre_check_point=None, after_check_point=None):
    """
    本omi只针对单层车
    :param self: ==self
    :param location_name:目的地库位名称
    :param follow_task:布尔值，是否有后置任务
    :param agv_type:执行任务的agv类型列表
    :param agv_id:指定执行任务的agv
    :param pre_task_id:前置任务
    :param layer:指定agv的层
    :param p4:None
    :param manage_mode:是否执行库管，True执行库管逻辑,False不执行库管逻辑
    :param pre_check_point:取货前检查点,如果配置了该参数，agv将在卸货前货前先导航到该检查点
    :param after_check_point:取货后检查点，如果配置了该参数，agv将在卸货后导航到该检查点
    :return:task_id
    """
    task_id = pre_task_id
    if pre_check_point:
        await set_order_status_and_logger(self=self, logger_info=f'前往卸货前检查点{pre_check_point}')
        task_id = await self.goto_location(pre_check_point, -1, True, agv_type, agv_id, task_id)
    # 卸货前判断车身上是否有货
    if agv_id and manage_mode:
        while True:
            agv_pallet_name = await self.get_location_pallet(f'RV{agv_id}-1')
            if agv_pallet_name:
                break
            else:
                await set_order_status_and_logger(self=self, logger_info=f'第{agv_id}号agv身上无货,无法执行卸货任务!')
            await self.ts_delay(0.5)

    # 锁定卸货库位
    await require_lock_location(self=self, location_name=location_name)
    # 判断库位是否已经处于已锁定库位列表中，若不在则添加进去
    if location_name not in global_location_locked:
        global_location_locked.append(location_name)
    await set_order_status_and_logger(self=self, logger_info=f'成功锁定库位{location_name}')
    # 判断是否带库管
    if manage_mode:
        while True:
            # 锁定库位后，卸货前判断库位上是否有货
            pallet_name = await self.get_location_pallet(location_name)
            if not pallet_name:
                await set_order_status_and_logger(self=self, logger_info=f'卸货位{location_name}上无货，agv将前往卸货!')
                break
            else:
                await set_order_status_and_logger(self=self,
                                                  logger_info=f'库位{location_name}上有货,无法前往执行卸货任务,请先移除在库位上的托盘!')
            await self.ts_delay(0.5)

    if after_check_point:
        task_id = await self.goto_location_unload(location_name, True, agv_type, agv_id, task_id, layer, p4,
                                                  manage_mode)
        await require_release_location(self=self, location_name=location_name)
        await set_order_status_and_logger(self=self, logger_info=f'卸货结束，前往卸货后检查点{after_check_point}')
        task_id = await self.goto_location(after_check_point, -1, follow_task, agv_type, agv_id, task_id)
    else:
        task_id = await self.goto_location_unload(location_name, follow_task, agv_type, agv_id, task_id, layer, p4,
                                                  manage_mode)
        await require_release_location(self=self, location_name=location_name)
    return task_id


# 获取能够执行任务的agv
async def goto_location_reserve(self, location_name, agv_type):
    task_id, agv_id = await self.goto_location_reserve(location_name, True, agv_type, None, None)
    return task_id, agv_id


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


async def add_pallet_to_location(self, pallet_name, pallet_type_id, pallet_batch_no, location):
    """
    向库位添加指定类型的托盘
    :param self: ==self
    :param pallet_name: 托盘名称
    :param pallet_type_id: 托盘类型id
    :param pallet_batch_no: 托盘批次号
    :param location: 设置托盘初始库位
    :return: pallet_id:返回托盘id
    """
    # 校验库位上是否有托盘
    while True:
        exists_pallet_name = await self.get_location_pallet(location)
        if not exists_pallet_name:
            await set_order_status_and_logger(self=self, logger_info='active')
            break
        await set_order_status_and_logger(self=self, logger_info=f'库位{location}上已存在托盘,无法添加托盘,请先移除改托盘.')
        await self.ts_delay(0.1)
    pallet_id = await self.add_pallet(pallet_name, pallet_type_id)
    if pallet_id == -1:
        await set_order_status_and_logger(self=self, logger_info=f'托盘类型{pallet_type_id}不存在,添加托盘{pallet_name}失败。',
                                          block=True, delay=30)
    if pallet_id == -2:
        await set_order_status_and_logger(self=self, logger_info=f'添加托盘{pallet_name}出现错误。', block=True, delay=30)
    if pallet_id == -3:
        await set_order_status_and_logger(self=self, logger_info='数据库错误,添加托盘失败', block=True, delay=30)
    await self.set_pallet_type(pallet_id, pallet_type_id)
    await self.set_pallet_batch_no(pallet_name, pallet_batch_no)
    await self.set_pallet_status(pallet_name, 1)
    result = await self.set_pallet_location(pallet_id, location)
    if result == -1:
        await set_order_status_and_logger(self=self, logger_info=f'托盘{pallet_name}不存在.', block=True, delay=30)
    if result == -2:
        await set_order_status_and_logger(self=self, logger_info=f'目标位置{location}上已有托盘，无法添加托盘', block=True, delay=30)
    if result == -3:
        await set_order_status_and_logger(self=self, logger_info=f'目标位置{location}被锁定', block=True, delay=30)
    return pallet_id


# 结束任务
async def finish_task(self, task_id, rest_api_ip_port):
    """
    :param self:==self
    :param task_id: 任务id
    :param rest_api_ip_port: restAPI服务ip和端口
    :return:
    """
    finish_task_api_url = f'http://{rest_api_ip_port}/api/dispatch/tasks/agv-tasks/completed/'
    await logger(self=self, logger_info=f'finish_task_api_url={finish_task_api_url}')
    request_data = json.dumps(dict(data=[dict(task_id=task_id)]))
    headers = {'Content-Type': 'application/json'}
    while True:
        try:
            res = requests.post(url=finish_task_api_url, data=request_data, headers=headers)
            await logger(self=self, logger_info=res.text)
            if json.loads(res.text).get('code') in [0, '0']:
                task_status = await check_task_status(self=self, task_id=task_id)
                if task_status == 'completed':
                    await set_order_status_and_logger(self=self, logger_info=f'已强制完成任务{task_id}')
                    break
            await set_order_status_and_logger(self=self, logger_info=f'强制完成任务{task_id}失败')
            await self.ts_delay(0.5)
        except Exception as e:
            error = json.dumps(e.args[0]).replace("'", "*")
            await set_order_status_and_logger(self=self, logger_info='结束任务{}失败,原因:{}'.format(task_id, error))
        await self.ts_delay(2)


# 查询任务状态
async def check_task_status(self, task_id, rest_api_ip_port):
    """
    :param self:==self
    :param task_id: 任务id
    :param rest_api_ip_port: restAPI服务ip和端口
    :return:
    """
    try:
        check_task_id_status_url = f'http://{rest_api_ip_port}/api/dispatch/tasks/{task_id}/status/'
        headers = {'Content-Type': 'application/json'}
        res = requests.get(url=check_task_id_status_url, timeout=3)
        await logger(self=self, logger_info=res.text)
        res_text = json.loads(res.text)
        if res_text.get('code') in [0, '0']:
            return res_text.get('data')[0].get('agv_task_status')
    except Exception as e:
        error = json.dumps(e.args[0]).replace("'", "*")
        await set_order_status_and_logger(self=self, logger_info=f'查询任务状态报错，报错原因:{error}')
    return


async def get_put_location_from_area(self, pallet_type, area_name_list):
    """
    从多库区巷道中选择能够放置托盘的库位并返回库位名称
    :param self: ==self
    :param pallet_type: 托盘类型
    :param area_name_list: 区域列表
    :return: area_name, location_name
    """
    put_location = None
    put_area = None
    for area in area_name_list:
        # 标记是否要检索下一个区域
        next_search = False
        # 获取区域检索权
        while True:
            check_area_status = await get_gp(self=self, key_name=f'area_{area}_status')
            await set_order_status_and_logger(self=self, logger_info=f'check_area_status={check_area_status}')
            # 判断库区是否已经被锁定
            if not check_area_status:
                await set_gp(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
                continue
            if 'locked' in check_area_status and check_area_status != f'area_locked_by_{self.order.order_id}':
                next_search = True
                break
            if check_area_status == f'{self.order.order_id}_searching':
                break
            await self.ts_delay(0.1)
        if next_search:
            # 释放当前区域搜索权限
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
        # 获取区域所有叶子节点
        leaf_location_names = await self.get_leaf_location_names(area)
        await set_order_status_and_logger(self=self,
                                          logger_info='leaf_location_names={}'.format('*'.join(leaf_location_names)))
        if not leaf_location_names:
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
        for location in leaf_location_names:
            # 判断库位是否有托盘
            p_pt = await self.get_location_pallet_and_type(location)
            p = p_pt[0][0]
            pt = p_pt[0][1]
            if not pt:
                put_area = area
                put_location = location
                continue
            check_pallet_type_id_sql = f"select id from layer2_pallet.object_type where name='{pt}' limit 1;"
            check_pallet_type_id_result = await self.run_sql(check_pallet_type_id_sql)
            pallet_type_id = check_pallet_type_id_result[0].get('id')
            # ========================================================
            await set_order_status_and_logger(self=self,
                                              logger_info=f'pallet_type_id={pallet_type_id}, pallet_type={pallet_type}')
            # ========================================================
            if str(pallet_type_id) == str(pallet_type):
                break
            else:
                put_area = None
                put_location = None
        if put_location:
            await set_gp(self=self, key_name=f'area_{area}_status', value=f'area_locked_by_{self.order.order_id}')
            break
        else:
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
    return put_area, put_location


async def get_fetch_location_from_area(self, pallet_type, area_name_list):
    """
    从多库区中选择能够取托盘的库位并返回库位名称
    :param self: ==self
    :param pallet_type: 存放的托盘类型
    :param area_name_list: 区域列表
    :return: location_name
    """
    fetch_location = None
    fetch_area = None
    for area in area_name_list:
        # 标记是否要检索下一个区域
        next_search = False
        # 获取区域检索权
        while True:
            check_area_status = await get_gp(self=self, key_name=f'area_{area}_status')
            if not check_area_status:
                await set_gp(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
                continue
            # 判断库区是否已经被锁定
            if 'locked' in check_area_status and check_area_status != f'area_locked_by_{self.order.order_id}':
                next_search = True
                break
            if check_area_status == f'{self.order.order_id}_searching':
                break
            await self.ts_delay(0.1)
        if next_search:
            # 释放当前区域搜索权限
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
        # 获取区域所有叶子节点
        leaf_location_names = await self.get_leaf_location_names(area)
        if not leaf_location_names:
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
        for location in leaf_location_names:
            # 判断库位是否有托盘
            p_pt = await self.get_location_pallet_and_type(location)
            p = p_pt[0][0]
            pt = p_pt[0][1]
            if not pt:
                continue
            fetch_area = area
            fetch_location = location
            check_pallet_type_id_sql = f"select id from layer2_pallet.object_type where name='{pt}' limit 1;"
            check_pallet_type_id_result = await self.run_sql(check_pallet_type_id_sql)
            pallet_type_id = check_pallet_type_id_result[0].get('id')
            if str(pallet_type_id) == str(pallet_type):
                break
            else:
                fetch_area = None
                fetch_location = None
        if fetch_location:
            await set_gp(self=self, key_name=f'area_{area}_status', value=f'area_locked_by_{self.order.order_id}')
            break
        else:
            await delete_gp_record(self=self, key_name=f'area_{area}_status', value=f'{self.order.order_id}_searching')
            continue
    return fetch_area, fetch_location


async def get_max_object_type_id(self):
    """
    获取object表中当前最大的object_type_id，若没有，则返回5
    :param self: ==self
    :return:
    """
    sql = "select max(object_type_id) as max_object_type_id from layer2_pallet.object;"
    result = await self.run_sql(sql)
    try:
        max_object_type_id = int(result[0].get('max_object_type_id'))
    except Exception as e:
        return 5
    return max_object_type_id


async def get_object_type_id(self, batch_no_like):
    """
    根据批次号模糊查询到托盘类型
    :param self: ==self
    :param batch_no_like: 批次号模糊查询字段
    :return: 托盘类型id
    """
    sql = f"select object_type_id from layer2_pallet.object where batch_no like '{batch_no_like}*%' limit 1;"
    result = await self.run_sql(sql)
    if not result:
        return None
    return result[0].get('object_type_id')
