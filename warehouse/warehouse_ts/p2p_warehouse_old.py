#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : LuBowen
# @Number  : 20210509
# @FileName  :ants_into_warehouse.py
# @Time      :2021/12/30 13:40
# @Software: PyCharm Community Edition
# @Version : Python3
# ====================================
from ts_template.ts_template import CancelException
from ts_template.ts_template import StopException
from ts_template.ts_exception import EnumOMErrorCode
import sys
import random
import asyncio
import pdb
from pathlib import Path
from datetime import datetime
import xml.dom.minidom
import time
import json
import requests

desc = 'ants车从输送线和工位搬运货物入库和出库'
# src:起点；dst:终点；group_id:任务组；order_id:任务组内任务序号
para_template = {
    'ants_into_warehouse': {'source': 'str',
                            'dest': 'str',
                            'group_id': 'str',
                            'sequence_id': 'str',
                            'scan_type': 'int',
                            'number': 'str',
                            'sku': 'str',
                            'process_type': 'str',
                            'dest_is_robot': 'str'}}
operator_list = []
agv_list = [4]

# 需要取货后立刻前往检查点的库位,该列表中的库位在取完货后如果无入库路线, agv不能在原地等待，必须前往等待区等待
location_check_point_mapping = ['Full-Up-1', 'Full-Up-2', 'Full-Up-3', 'Full-Up-4', 'Full-Up-5', 'Full-Up-6',
                                'Full-Up-7', 'Full-Up-8', 'Full-Up-9', 'Full-Up-10', 'Full-Up-11', 'Full-Up-12',
                                'Empty-Up-1', 'Empty-Up-2', 'Empty-Up-3', 'Empty-Up-4']
# 等待区域名称列表(根据现场实际情况配置)
waiting_area_name_list = ['warehouse-check-area']
# 等待区外对应的排队点，每一个等待区外都有一个排队点，当等待区内无位置时，所有agv都要在排队点排队
waiting_area_check_point = {'warehouse-check-area': 'warehouse-check-dock'}
# 配置等待区域名称
waiting_area = 'arm-check-area'
# restAPI服务ip,端口
restAPI_ip = '127.0.0.1'
restAPI_port = 6767
# 宏定义库区名称
location_area_name = 'location_area'
time_spend_in_waiting_limit = 120


async def run(self):
    # 宏定义订单锁，用于锁定任务执行过程中的库位
    lock = f'order_{self.order.order_id}'
    # 1:点到点；2：点到区域；3：区域到点；4：区域到区域
    process_mode = 0
    try:
        src = self.source
        dst = self.dest
        process_type = self.process_type
        group_id = self.group_id
        sequence_id = self.sequence_id
        scan_type = self.scan_type
        number = self.number
        sku = self.sku
        dest_is_robot = self.dest_is_robot

        check_src = await check_location(self=self, location_name=src)
        check_dst = await check_location(self=self, location_name=dst)
        if not (check_src and check_dst):
            await self.ts_delay(120)
            return 0
        await set_logger(self=self, log_info='校验库位成功')
        if process_type in [0, '0']:
            check_src_in_area = not await is_area(self=self, location_name=src)
            check_dst_in_area = not await is_area(self=self, location_name=dst)
            if not (check_src_in_area and check_dst_in_area) and self.source != self.dest:
                await self.update_order_status('you send a wrong process_type!')
                return 504
            if self.source != self.dest:
                process_mode = 1
            else:
                process_mode = 5
        elif process_type in [1, '1']:
            check_src_in_area = not await is_area(self=self, location_name=src)
            check_dst_in_area = await is_area(self=self, location_name=dst)
            await self.log(f'check_src44444444444{str(check_src_in_area)}5555555555{str(check_dst_in_area)}')
            if not (check_src_in_area and check_dst_in_area):
                await self.update_order_status('you send a wrong process_type!')
                return 504
            process_mode = 2
        elif process_type in [2, '2']:
            check_src_in_area = await is_area(self=self, location_name=src)
            check_dst_in_area = not await is_area(self=self, location_name=dst)
            if not (check_src_in_area and check_dst_in_area):
                await self.update_order_status('you send a wrong process_type!')
                return 504
            process_mode = 3
        elif process_type in [3, '3']:
            check_src_in_area = await is_area(self=self, location_name=src)
            check_dst_in_area = await is_area(self=self, location_name=dst)
            if not (check_src_in_area and check_dst_in_area):
                await self.update_order_status('you send a wrong process_type!')
                return 504
            process_mode = 4
        else:
            await self.update_order_status('you send a wrong scan_type!')
            return 504
        try:
            group_id = int(self.group_id)
            order_id = int(self.sequence_id)
        except Exception as e:
            await self.set_order_error('have no params')
            await self.ts_delay(120)
            return 504
        await set_logger(self=self, log_info='校验group_id和sequence_id成功')
        # 区域到点
        if process_mode in [3, 4]:
            pallet = await check_pallet(self=self, location_name=f'{src}_u')
            if not pallet:
                await self.ts_delay(120)
                return 0
            await set_logger(self=self, log_info='取货点在库区中，下发出库任务')
            await out_warehouse_task(self=self, src=src, dst=dst, lock=lock)
        # 点到区域
        elif process_mode in [1, 2]:
            if process_mode == 2:
                await set_logger(self=self, log_info='去取货点在库区外，下发入库任务')
                # 从waiting_area获取等待点waiting_point，无等待点则在区域外排队
                await into_warehouse_task(self=self, src=src, dst=dst, lock=lock, waiting_point=None)
            else:
                await set_logger(self=self, log_info='取货点与卸货点都在库区外')
                await general_p2p(self, src, dst, agv_list, None, False)
        elif process_mode in [5]:
            await inventory_function(self, dst=dst, agv_list=agv_list, need_post=1)
        else:
            return 504
        await set_gp(self=self, key_name=f'group_{group_id}_order_{order_id}', value='finish')
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
        self.order.error_code = EnumOMErrorCode.TS_MANUALLY_SET_ORDER_ERROR
        await self.run_sql(
            f"update layer4_1_om.globalparameters set gp_value = 'none' where gp_value ='order_{str(self.order.order_id)}';")
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        return 504


async def cancel(self):
    try:
        require_lock = await self.get_gp('require_lock_location_permission')
        if require_lock == f'order_{str(self.order.order_id)}':
            await self.set_gp('require_lock_location_permission', 'none', 'str')
    except:
        pass
    flag = await is_area(self, self.source)
    if flag:
        try:
            await self.add_pallet(f"{self.source}_u", 1)
            await self.add_pallet(f"{self.source}_d", 1)
            await self.add_pallet(f"{self.source}_r", 1)
            await self.add_pallet(f"{self.source}_l", 1)
        except:
            pass
    else:
        try:
            await self.add_pallet(f"{self.source}", 1)
        except:
            pass
    await self.run_sql(
        f"update layer4_1_om.globalparameters set gp_value = 'none' where gp_value ='order_{str(self.order.order_id)}';")
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


async def report_to_mes(self, json_data, blocking=True, debug=False):
    """
    :param self: self=self
    :param json_data: 上报数据json格式
    :param blocking: 是否阻塞，默认请求阻塞（True），即请求不成功会一直请求
    :param debug: 是否处于调试模式，为True时表示处于调试模式，此模式下将不向mes上报信息
    :return: None
    """

    if not debug:
        return
    url = ''
    headers = {'Content-Type': 'application/json'}
    while True:
        try:
            res = requests.post(url=url, headers=headers, data=json_data)
            res_dict = json.loads(res.text)
            self.logger.info('res_text={}'.format(res.text))
            if res_dict.get('code') in [0, '0']:
                break
        except Exception as e:
            self.logger.error(e)
        if not blocking:
            break
        await self.ts_delay(5)


# 同组订单执行顺序锁定
async def order_start(self, group_id, order_id):
    group_id = int(group_id)
    order_id = int(order_id)
    await set_gp(self=self, key_name=f'group_{str(group_id)}_order_{str(order_id)}', value='start')
    if order_id in [1, '1']:
        return
    while True:
        check_group_order = await get_gp(self=self, key_name=f'group_{str(group_id)}_order_{str(order_id - 1)}')
        if check_group_order == 'finish':
            return
        await self.update_order_status(f'wait for task group_id_{str(group_id)}_order_id_{str(order_id - 1)} end')
        await self.ts_delay(10)


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
        result = await execute_sql(self=self, sql=check_sql)
        if not result:
            await self.set_order_error('have no location')
            pass
        else:
            return_location_name = location_name
    except Exception as e:
        pass
        await self.set_order_error('have no location')
    return return_location_name


# 校验托盘是否存在
async def check_pallet(self, location_name):
    """
    :param self: ==self
    :param location_name: 库位名称
    :return:
    """
    return_location_name = None
    try:
        check_sql = '''select id from layer2_pallet.object where object_name=\'{}\';'''.format(
            location_name)
        result = await execute_sql(self=self, sql=check_sql)
        if not result:
            pass
            await self.set_order_error('have no pallet')
        else:
            return_location_name = location_name
    except Exception as e:
        pass
        await self.set_order_error('have no pallet')
    return return_location_name


# 申请对库位进行加锁的权限,只有获得加锁权限的订单才可以对库位进行加锁
async def require_lock_location_permission(self, permission_lock):
    """
    :param self: ==self
    :param permission_lock:
    :return:
    """
    key_name = 'require_lock_location_permission'
    while True:
        require_lock_location_permission_lock = await get_gp(self=self, key_name=key_name)
        if require_lock_location_permission_lock == permission_lock:
            return
        if require_lock_location_permission_lock == 'none':
            await set_gp(self=self, key_name=key_name, value=permission_lock)
            return
        if not require_lock_location_permission_lock:
            await set_gp(self=self, key_name=key_name, value='none')
            return
        await self.ts_delay(10)


# 释放库位加锁的权限
async def release_lock_location_permission(self, permission_lock):
    """
    :param self: ==self
    :param permission_lock: 锁
    :return:
    """
    key_name = 'require_lock_location_permission'
    while True:
        require_lock_location_permission_lock = await get_gp(self=self, key_name=key_name)
        if require_lock_location_permission_lock != permission_lock:
            return
        if require_lock_location_permission_lock == permission_lock:
            await set_gp(self=self, key_name=key_name, value='none')
        await self.ts_delay(5)


# 对库区中agv要经过的库位进行加锁，并提升其他库位的权重
async def lock_location(self, location_name_list, lock):
    """
    :param self: ==self
    :param location_name_list: 要锁定的库位名称列表，一锁全锁
    :param lock:锁
    :return: 库位全部锁定成功，返回已被锁定的库位列表
    """
    location_has_locked = []
    await require_lock_location_permission(self=self, permission_lock=lock)
    # 校验要加锁的库位是否已被加锁
    for location in location_name_list:
        location_name_current_lock = await get_gp(self=self, key_name=location)
        if location_name_current_lock and location_name_current_lock not in ['none', lock]:
            # 某个库位加锁不成功,释放全部已加锁的库位
            await release_location(self=self, location_name_list=location_has_locked, lock=lock)
            # # 释放加锁权限
            await release_lock_location_permission(self=self, permission_lock=lock)
            return []
        else:
            if 'Empty-Up' not in location and 'Empty-Down' not in location:
                await set_gp(self=self, key_name=location, value=lock)
                location_has_locked.append(location)
            else:
                await release_lock_location_permission(self=self, permission_lock=lock)
                return True
    await release_lock_location_permission(self=self, permission_lock=lock)
    return location_has_locked


# 释放库位锁
async def release_location(self, location_name_list, lock):
    """
    :param self: ==self
    :param location_name_list: 要解锁的库位列表
    :param lock: 锁
    :return: none
    """
    for location in location_name_list:
        location_current_status = await get_gp(self=self, key_name=location)
        if location_current_status == lock:
            await set_gp(self=self, key_name=location, value='none')
    return


# 请求新卸货点
async def require_new_dst(self, request_data, blocking=False):
    """
    :param self: ==self
    :param request_data:请求参数
    :param blocking: 请求是否阻塞，False为非阻塞，请求失败也会退出
    :return:
    """
    headers = {'Content-Type': 'application/json'}
    fail_time = 1
    while True:
        try:
            url = await self.get_gp('base_url')
            res = requests.post(url=f"{url}/api/om/order/update_location2/", data=json.dumps(request_data),
                                headers=headers, timeout=20).content
            self.logger.debug(f'{str(res)}_ask_new_location')
            break
        except Exception as e:
            self.logger.error(str(e))
            await self.ts_delay(5)
    new_dst = json.loads(res)
    return True, new_dst['newLocation']


# 结束任务
async def finish_task(self, task_id):
    """
    :param self:==self
    :param task_id: 任务id
    :return:
    """
    # finish_task_api_url = f'http://{restAPI_ip}:{restAPI_port}/api/dispatch/tasks/agv-tasks/completed/'
    # set_logger(self=self, log_info=f'finish_task_api_url={finish_task_api_url}')
    # request_data = json.dumps(dict(data=[dict(task_id=task_id)]))
    # headers = {'Content-Type': 'application/json'}
    while True:
        try:
            # res = requests.post(url=finish_task_api_url, data=request_data, headers=headers)
            # await set_logger(self=self, log_info=f'res={res}')
            # await set_logger(self=self, log_info=f'res_text={res.text}')
            await self.set_agv_task_status(task_id, 'finish')
            task_status = await self.is_task_finished(task_id)
            if task_status == 0:
                break
        except Exception as e:
            await self.update_order_status('End task {} failed,{}'.format(task_id, e))
            await self.log(e)
        await self.ts_delay(5)


# async def finish_task(self, task_id):
#     """
#     :param self:==self
#     :param task_id: 任务id
#     :return:
#     """
#     finish_task_api_url = f'http://{restAPI_ip}:{restAPI_port}/api/dispatch/tasks/agv-tasks/completed/'
#     set_logger(self=self, log_info=f'finish_task_api_url={finish_task_api_url}')
#     request_data = json.dumps(dict(data=[dict(task_id=task_id)]))
#     headers = {'Content-Type': 'application/json'}
#     while True:
#         try:
#             res = requests.post(url=finish_task_api_url, data=request_data, headers=headers)
#             await set_logger(self=self, log_info=f'res={res}')
#             await set_logger(self=self, log_info=f'res_text={res.text}')
#             if json.loads(res.text).get('code') in [0, '0']:
#                 task_status = await self.is_task_finished(task_id)
#                 if task_status == 0:
#                     break
#         except Exception as e:
#             await self.update_order_status('结束任务{}失败,原因:{}'.format(task_id, e))
#             await self.log(e)
#         await self.ts_delay(5)


# 查询任务状态
async def check_task_status(self, task_id):
    """
    :param self:==self
    :param task_id: 任务id
    :return:
    """
    try:
        check_task_id_status_url = f'http://{restAPI_ip}:{restAPI_port}/api/dispatch/tasks/{task_id}/status/'
        await set_logger(self=self, log_info=f'check_task_id_status_url={check_task_id_status_url}')
        headers = {'Content-Type': 'application/json'}
        res = requests.get(url=check_task_id_status_url, timeout=3)
        await set_logger(self=self, log_info=f'res={res}')
        res_text = json.loads(res.text)
        await set_logger(self=self, log_info=f'res_text={res_text}')
        if res_text.get('code') in [0, '0']:
            return res_text.get('data')[0].get('agv_task_status')
    except Exception as e:
        await self.log(e)
    return


# async def p2p_task(self, src, dst, lock, scan_type, waiting_point=None):
#     # 锁定取货工位
#     while True:
#         src_lock_status = await lock_location(self=self, location_name_list=[src], lock=lock)
#         if src_lock_status:
#             await self.update_order_status('active')
#             break
#         else:
#             await self.update_order_status('库位{}已被其他车辆锁定,本任务等待中'.format(src))
#         await self.ts_delay(2)
#     task_id, agv_id = await self.goto_location_reserve(src, True, [4], None, None)
#     await set_logger(self=self, log_info='锁定取货位，agv前往取货')
#     new_dst, pallet_name, task_id = await goto_load_with_scan_code(self=self, group_id=self.group_id,
#                                                                    scan_type=self.scan_type,
#                                                                    sequence_id=self.sequence_id,
#                                                                    location=src, taskid=task_id, agv_list=agv_list,
#                                                                    agv_id=agv_id)


# 工位入库业务
async def into_warehouse_task(self, src, dst, lock, waiting_point=None):
    """
    :param self: ==self
    :param src: 起点
    :param dst: 终点
    :param lock: 锁
    :param waiting_point: 等待点，若有等待点，车辆取完货会立即前往等待点，无则原地等待
    :return: 0
    """
    check_src_in_area = await is_area(self=self, location_name=src)
    if check_src_in_area:
        src = f'{src}_u'
    dst = dst
    # 是否已发送导航任务
    has_send_navigation_task = False
    # 导航任务id
    navigation_task_id = None
    # 导航任务是否结束
    navigation_end = False
    # 等待开始时间
    time_spend_in_waiting_start = time.time()
    # 等待结束时间
    time_spend_in_waiting_end = time.time()
    dst_route_location_list = []
    lock_result = []
    # 判断前一个订单是否完成，前一个订单完成后本订单才能继续执行
    await order_start(self=self, group_id=self.group_id, order_id=self.sequence_id)
    # 锁定取货工位
    while True:
        src_lock_status = await lock_location(self=self, location_name_list=[src], lock=lock)
        if src_lock_status:
            await self.update_order_status('active')
            break
        else:
            await self.update_order_status(
                'Location {} has been locked by other vehicles, and this task is pending'.format(src))
        await self.ts_delay(20)
    await set_logger(self=self, log_info='锁定取货位，agv前往取货')
    # 选择agv前往执行任务
    is_src_in_area = await is_area(self=self, location_name=src)
    await set_logger(self=self, log_info='判断起点是否为库区库位')
    if is_src_in_area:
        await set_logger(self=self, log_info='起点位于库区')
        task_id, agv_id = await self.goto_location_reserve(f'{src}_u', True, [4], None, None)
    else:
        await set_logger(self=self, log_info='起点不位于库区')
        task_id, agv_id = await self.goto_location_reserve(src, True, [4], None, None)
    # 释放所有边
    # await reset_edge_weight_enable(self=self, location_list=[], agv_id=agv_id)
    # 空车前往取货
    if 'Empty-Up' in self.source:
        location_infor = await self.run_sql(
            f'''select * from location where location_name = \'{self.source}\'''')
        check_dst = await self.get_mapping_value(location_infor[0]['id'], 5)
        if check_dst:
            task_id = await self.goto_location(check_dst[0], 2, True, agv_list, agv_id, task_id)
    new_dst, pallet_name, task_id = await goto_load_with_scan_code(self=self, group_id=self.group_id,
                                                                   scan_type=self.scan_type,
                                                                   sequence_id=self.sequence_id,
                                                                   location=src, taskid=task_id, agv_list=agv_list,
                                                                   agv_id=agv_id)
    await self.run_sql(f'''update location set can_put = True where location_name = \'{self.source}\'''')
    # await self.run_sql(f'''update location set is_booked = False where location_name = \'{self.source}\'''')
    await set_logger(self=self, log_info='取货完成，返回{}，{}，{}'.format(new_dst, pallet_name, task_id))
    # task_id = await self.goto_location_load(src, True, [4], agv_id, task_id)
    # 取货结束，解锁起点库位
    # await release_location(self=self, location_name_list=[src], lock=lock)
    # await set_logger(self=self, log_info='释放取货点成功')
    waiting_point = None
    if self.source in location_check_point_mapping:
        for waiting_area_name in waiting_area_name_list:
            # waiting_point = location_check_point_mapping.get(src)
            waiting_point, _ = await self.get_put_location_by_rule([waiting_area_name], 5, book=False)
            if waiting_point:
                lock_waiting_point_be_chosen = await self.require_lock_location(waiting_point)
                if not lock_waiting_point_be_chosen:
                    break
        if not waiting_point:
            waiting_point = waiting_area_check_point.get(waiting_area_name_list[0])
    await set_logger(self=self, log_info='获取取货等待点{}'.format(waiting_point))
    if waiting_point:
        await set_logger(self=self, log_info='导航前往等待点')
        while True:
            if navigation_task_id:
                # 校验导航是否结束，若已结束则开始计算agv等待时间
                check_navigation_status = await self.is_task_finished(navigation_task_id)
                if check_navigation_status == 0 and not navigation_end:
                    # 标记等待开始时间
                    time_spend_in_waiting_start = time.time()
                    navigation_end = True
            if not has_send_navigation_task:
                location_infor = await self.run_sql(
                    f'''select * from location where location_name = \'{self.source}\'''')
                check_dst = await self.get_mapping_value(location_infor[0]['id'], 2)
                if check_dst:
                    task_id = await self.goto_location_act_c(check_dst[0], 1, True, agv_list, agv_id, task_id)
                    io_id = await self.get_mapping_value(location_infor[0]['id'], 3)
                    while (1):
                        finish_flag = await self.is_task_finished(task_id)
                        if finish_flag == 0:
                            break
                        if io_id:
                            await self.set_ssio(io_id[0], 0, 17)
                        await self.ts_delay(0.5)
                else:
                    io_id = await self.get_mapping_value(location_infor[0]['id'], 3)
                    if io_id:
                        await self.ts_delay(1)
                        await self.set_ssio(io_id[0], 0, 17)
                task_id = await self.goto_location_c(waiting_point, 2, True, [4], agv_id, task_id)
                await release_location(self=self, location_name_list=[src], lock=lock)
                await set_logger(self=self, log_info='释放取货点成功')
                has_send_navigation_task = True
                navigation_task_id = task_id
                continue
            else:
                _, dst_route_location_list = await Route_main(self, src, dst)
                await set_logger(self=self, log_info='搜索前往卸货点库位路线成功:{}'.format(dst_route_location_list))
                if dst_route_location_list:
                    lock_result = await lock_location(self=self, location_name_list=dst_route_location_list, lock=lock)
                    await set_logger(self=self, log_info='成功锁定卸货路线{}'.format(dst_route_location_list))
                    if lock_result:
                        # 卸货点路线畅通，结束导航任务，前往卸货点卸货
                        await finish_task(self, task_id)
                        await release_location(self=self, location_name_list=[waiting_point], lock=lock)
                        # 变更路线权重
                        await reset_edge_weight(self=self, location_list=dst_route_location_list, agv_id=agv_id)
                        break
            if ((time_spend_in_waiting_end - time_spend_in_waiting_start) > time_spend_in_waiting_limit) \
                    and navigation_end:
                require_result, new_dst = await require_new_dst(self, request_data={"orderID": self.order.order_id,
                                                                                    "currentLocation": dst,
                                                                                    "operationType": "1"})
                self.logger.info(f'''{str(require_result)}________________{str(new_dst)}''')
                if require_result and dst != new_dst:
                    dst = new_dst
                    # 新卸货点确定，重置等待时间
                    time_spend_in_waiting_start = time.time()
            time_spend_in_waiting_end = time.time()
            await self.ts_delay(5)
    else:
        has_task = False
        await set_logger(self=self, log_info='无取货等待点，agv原地等待')
        time_spend_in_waiting_start = time.time()
        while True:
            location_infor = await self.run_sql(
                f'''select * from location where location_name = \'{self.source}\'''')
            check_dst = await self.get_mapping_value(location_infor[0]['id'], 2)
            if not has_task:
                if check_dst:
                    task_id = await self.goto_location_act_c(check_dst[0], 1, True, agv_list, agv_id, task_id)
                    io_id = await self.get_mapping_value(location_infor[0]['id'], 3)
                    while (1):
                        finish_flag = await self.is_task_finished(task_id)
                        if finish_flag == 0:
                            break
                        if io_id:
                            await self.set_ssio(io_id[0], 0, 17)
                        await self.ts_delay(0.5)
                has_task = True
            _, dst_route_location_list = await Route_main(self, src, dst)
            await set_logger(self=self, log_info='搜索前往卸货点库位路线成功:{}'.format(dst_route_location_list))
            if dst_route_location_list:
                lock_result = await lock_location(self=self, location_name_list=dst_route_location_list, lock=lock)
                if lock_result:
                    await reset_edge_weight(self=self, location_list=dst_route_location_list, agv_id=agv_id)
                    await set_logger(self=self, log_info='成功锁定卸货路线{}'.format(dst_route_location_list))
                    break
                await set_logger(self=self, log_info='加锁前往卸货点库位路线失败:{}'.format(dst_route_location_list))
                await self.update_order_status('Route occupied')
            if (time_spend_in_waiting_end - time_spend_in_waiting_start) > time_spend_in_waiting_limit:
                await set_logger(self=self, log_info='等待超时，重新申请卸货点')
                require_result, new_dst = await require_new_dst(self, request_data={"orderID": self.order.order_id,
                                                                                    "currentLocation": dst,
                                                                                    "operationType": "1"})
                if require_result:
                    await set_logger(self=self, log_info='重新申请卸货点成功，变更卸货点{}'.format(new_dst))
                    dst = new_dst
                    # 新卸货点确定，重置等待时间
                    time_spend_in_waiting_start = time.time()
                    await set_logger(self=self, log_info='成功重置等待时间')
            time_spend_in_waiting_end = time.time()
            await self.ts_delay(5)
    if dst_route_location_list:
        await set_logger(self=self, log_info='搜索卸货路线{}成功，发送卸货任务'.format(dst_route_location_list))
        await release_location(self=self, location_name_list=[src], lock=lock)
        await set_logger(self=self, log_info='释放取货点成功')
        task_id = await goto_unload_with_check_area_and_report_code(self=self, location=dst_route_location_list[-1],
                                                                    location_name_list=None, scan_type=self.scan_type,
                                                                    taskid=task_id,
                                                                    agv_list=agv_list,
                                                                    agv_id=agv_id, code=pallet_name)
        # await self.run_sql(f'''update location set can_put = False where location_name = \'{self.dest}\'''')
        # task_id = await self.goto_location_act(dst_route_location_list[-1], 1, False, [4], agv_id, task_id)
    else:
        # task_id = await self.goto_location_act(dst, 1, False, [4], agv_id, task_id)
        await release_location(self=self, location_name_list=[src], lock=lock)
        await set_logger(self=self, log_info='释放取货点成功')
        if 'Empty-Down' in self.dest:
            location_infor = await self.run_sql(
                f'''select * from location where location_name = \'{self.dest}\'''')
            check_dst = await self.get_mapping_value(location_infor[0]['id'], 5)
            if check_dst:
                task_id = await self.goto_location(check_dst[0], 2, True, agv_list, agv_id, task_id)
        task_id = await goto_unload_with_check_area_and_report_code(self=self, location=dst, location_name_list=None,
                                                                    scan_type=self.scan_type, taskid=task_id,
                                                                    agv_list=agv_list,
                                                                    agv_id=agv_id, code=pallet_name)
        # await self.run_sql(f'''update location set can_put = False where location_name = \'{self.dest}\'''')
    if lock_result:
        await release_location(self=self, location_name_list=lock_result, lock=lock)
    await set_logger(self=self, log_info='成功释放卸货路线{}'.format(dst_route_location_list))
    return task_id


# 设置agv行走的边权重
async def reset_edge_weight(self, location_list, agv_id):
    """
    :param self: ==self
    :param location_list: agv行驶路线经过的库位列表库位
    :param agv_id: agv编号
    :return:
    """
    disable_edges = await get_disable_edges(self=self, location_list=location_list)
    await set_logger(self=self, log_info='获取库位{}所在边列表{}'.format(location_list, disable_edges))
    flag = await disable_edge(self=self, agv_id=agv_id, edges=disable_edges)
    await set_logger(self=self, log_info='锁定{}成功'.format(disable_edges))
    ret = await check_disable_edge(self=self, agv_id=agv_id)


async def reset_edge_weight_unable(self, location_list, agv_id):
    """
        :param self: ==self
        :param location_list: agv行驶路线经过的库位列表库位
        :param agv_id: agv编号
        :return:
        """
    disable_edges = await enable_all_edge(self=self)
    await set_logger(self=self, log_info='获取库位{}所在边列表{}'.format(location_list, disable_edges))
    flag = await disable_edge(self=self, agv_id=agv_id, edges=disable_edges, set_type='false')
    await set_logger(self=self, log_info='锁定{}成功'.format(disable_edges))
    ret = await check_disable_edge(self=self, agv_id=agv_id)


# 设置agv行走的边权重
async def reset_edge_weight_enable(self, location_list, agv_id):
    """
    :param self: ==self
    :param location_list: agv行驶路线经过的库位列表库位
    :param agv_id: agv编号
    :return:
    """
    disable_edges = await enable_all_edge(self=self)
    await set_logger(self=self, log_info='获取库位{}所在边列表{}'.format(location_list, disable_edges))
    flag = await disable_edge(self=self, agv_id=agv_id, edges=disable_edges)
    await set_logger(self=self, log_info='锁定{}成功'.format(disable_edges))
    ret = await check_disable_edge(self=self, agv_id=agv_id)


async def enable_all_edge(self):
    get_edge_sql = f"""select string_agg(CAST(edge_id as varchar), ',') as edge_text from public.location_edge;"""
    await self.log(f'#################{get_edge_sql}#######################')
    edge_text = await execute_sql(self=self, sql=get_edge_sql)
    await self.log(f'########################{edge_text}#############################')
    if not edge_text:
        return []
    else:
        edges = edge_text[0].get('edge_text').split(',')
        await set_logger(self=self, log_info=f'edges={edges}')
        edge_list = [i for i in edges]
    return edge_list


# 获取
async def get_disable_edges(self, location_list):
    """
    获取库区内所有不在location_list中的库位，将其所在边查询出来
    :param self: ==self
    :param location_list: 过滤边的库位列表
    :return:
    """
    get_edge_sql = f"""select string_agg(CAST(edge_id as varchar), ',') as edge_text from public.location_edge where location_name in (\'{"','".join(location_list)}\');"""
    await self.log(f'#################{get_edge_sql}#######################')
    edge_text = await execute_sql(self=self, sql=get_edge_sql)
    await self.log(f'########################{edge_text}#############################')
    if not edge_text:
        return []
    else:
        if not edge_text:
            return []
        edges = edge_text[0].get('edge_text').split(',')
        edge_list = [int(i) for i in edges]
    return edge_list


# 禁用边
async def disable_edge(self, agv_id: int, edges: list, set_type='true'):
    """
    禁用所有agv行驶路径中位于edges中的边
    :param self: ==self
    :param agv_id: agv标号
    :param edges: 边列表
    :param set_type: 设置模式，true开放， false禁用
    :return:
    """
    for edge in edges:
        disable_edge_sql = "select out_result_code from set_map_command('dispatch', array[cast(row('{%d}', null, 1, null, null, '{%s}', null, '%s', 1) as map_agv_override_type)]);" % (
            agv_id, edge, set_type)
        ret = await execute_sql(self=self, sql=disable_edge_sql)
        if len(ret) > 0 and ret[0]["out_result_code"] != 0:
            self.logger.info(f'disable_edge failed! {ret}')
            return False
        self.logger.info(f'disable_edge success! {ret}')
    return True


# 校验禁用边结果
async def check_disable_edge(self, agv_id: int):
    """
    禁用边之后需要做校验是否禁用成功
    :param self: ==self
    :param agv_id: agv标号
    :return:
    """
    check_disable_edge = f"select * from get_map_command('dispatch', {agv_id}, null, null, null, null)limit 1;"
    ret = await execute_sql(self=self, sql=check_disable_edge)
    if len(ret) > 0:
        self.logger.info(f'check_disable_edge failed! {ret}')
        return False
    self.logger.info(f'check_disable_edge success! {ret}')
    return True


# 出库任务
async def out_warehouse_task(self, src, dst, lock):
    """
    :param self: ==self
    :param src: 取货点
    :param dst: 卸货点
    :param lock: 锁
    :return:
    """
    src = src
    dst = dst
    while True:
        # 搜索前往取货退出路线
        src_route_location_list, _ = await Route_main(self, src, dst)
        await set_logger(self=self, log_info='搜索取货退出路线{}'.format(src_route_location_list))
        if not src_route_location_list:
            await self.update_order_status(f'The exit route after going to {src} is temporarily blocked')
            await self.ts_delay(5)
            continue
        else:
            await set_logger(self=self, log_info=f'获取取货退出路线{src_route_location_list}')
            src_location_has_been_locked = await lock_location(self=self, location_name_list=src_route_location_list,
                                                               lock=lock)
            # dst_location_has_been_locked = await lock_location(self=self, location_name_list=dst_route_location_list,
            #                                                    lock=lock)
            # 选择agv前往执行任务
            task_id, agv_id = await self.goto_location_reserve(src_route_location_list[0], True, [4], None, None)
            # 释放所有边
            # await reset_edge_weight_enable(self=self, location_list=[], agv_id=agv_id)
            # task_id = await self.goto_location_load(src, True, [4], agv_id, task_id)
            await set_logger(self=self, log_info='路线锁定成功，车辆选择成功，正在生成取货任务')
            # 变更卸货路径权重
            await reset_edge_weight(self=self, location_list=src_route_location_list, agv_id=agv_id)
            await set_logger(self=self, log_info='变更取货退出路线权重结束')
            new_dst, code, task_id = await goto_load_with_scan_code(self=self, location=src_route_location_list[0],
                                                                    scan_type=self.scan_type,
                                                                    group_id=self.group_id,
                                                                    sequence_id=self.sequence_id,
                                                                    taskid=task_id, agv_list=agv_list, agv_id=agv_id)
            await reset_edge_weight(self=self, location_list=src_route_location_list, agv_id=agv_id)
            # await reset_edge_weight_unable(self=self, location_list=[], agv_id=agv_id)
            # 判断终点库位是否在库区
            check_dst = await is_area(self=self, location_name=dst)
            if check_dst:
                while True:
                    # await reset_edge_weight(self=self, location_list=src_route_location_list, agv_id=agv_id)
                    await release_location(self=self, location_name_list=src_route_location_list, lock=lock)
                    _, dst_route_location_list = await Route_main(self, src, dst)
                    if not dst_route_location_list:
                        await self.update_order_status(f'The route to {dst} is temporarily blocked')
                        await self.ts_delay(5)
                        continue
                    else:
                        break
                dst_location_has_been_locked = await lock_location(self=self,
                                                                   location_name_list=dst_route_location_list,
                                                                   lock=lock)
                await set_logger(self=self, log_info=f'获取到前往{dst}的路线{dst_route_location_list}')
                await reset_edge_weight(self=self, location_list=src_route_location_list + dst_route_location_list,
                                        agv_id=agv_id)
                await set_logger(self=self, log_info=f'变更{dst}路线权重, 下发卸货任务')
                if 'Empty-Down' in self.dest:
                    location_infor = await self.run_sql(
                        f'''select * from location where location_name = \'{self.dest}\'''')
                    check_dst = await self.get_mapping_value(location_infor[0]['id'], 5)
                    if check_dst:
                        task_id = await self.goto_location(check_dst[0], 2, True, agv_list, agv_id, task_id)
                task_id = await goto_unload_with_check_area_and_report_code(self=self,
                                                                            location=dst_route_location_list[-1],
                                                                            location_name_list=None,
                                                                            code=code,
                                                                            scan_type=self.scan_type,
                                                                            taskid=task_id,
                                                                            agv_list=agv_list,
                                                                            agv_id=agv_id)
                # await self.run_sql(f'''update location set can_put = False where location_name = \'{self.dest}\'''')
                # 判断车辆是否出库区已决定是否释放库位
                while True:
                    # 获取车辆当前坐标
                    pos_x, pos_y, pos_angle = await self.get_agv_pos(agv_id)
                    agv_is_out = await is_outof_area(self=self, location_name=f'{src}_u', x=pos_x, y=pos_y)
                    if agv_is_out:
                        await release_location(self=self, location_name_list=src_location_has_been_locked, lock=lock)
                        await set_logger(self=self, log_info='取货路线库位解锁成功')
                        break
                    await self.ts_delay(5)
                # 检验卸货任务是否完成
                while True:
                    check_unload_task_end = await self.is_task_finished(task_id)
                    if check_unload_task_end == 0:
                        await release_location(self=self, location_name_list=dst_location_has_been_locked, lock=lock)
                        await set_logger(self=self, log_info=f'卸货结束，释放卸货路线库位{dst_location_has_been_locked}')
                        break
                    await self.ts_delay(5)
            else:
                await reset_edge_weight(self=self, location_list=src_route_location_list, agv_id=agv_id)
                if 'Empty-Down' in self.dest:
                    location_infor = await self.run_sql(
                        f'''select * from location where location_name = \'{self.dest}\'''')
                    check_dst = await self.get_mapping_value(location_infor[0]['id'], 5)
                    if check_dst:
                        task_id = await self.goto_location(check_dst[0], 2, True, agv_list, agv_id, task_id)
                task_id = await goto_unload_with_check_area_and_report_code(self=self, location=dst,
                                                                            location_name_list=src_location_has_been_locked,
                                                                            scan_type=self.scan_type,
                                                                            taskid=task_id, agv_list=agv_list,
                                                                            agv_id=agv_id, code=code)
                await self.run_sql(f'''update location set can_put = False where location_name = \'{self.dest}\'''')
                while True:
                    # 获取车辆当前坐标
                    pos_x, pos_y, pos_angle = await self.get_agv_pos(agv_id)
                    agv_is_out = await is_outof_area(self=self, location_name=src_route_location_list[0], x=pos_x,
                                                     y=pos_y)
                    if agv_is_out:
                        await release_location(self=self, location_name_list=src_location_has_been_locked, lock=lock)
                        break
                    await self.ts_delay(5)
                await release_location(self=self, location_name_list=src_location_has_been_locked, lock=lock)

            await self.run_sql(f'''update location set can_put = True where location_name = \'{self.source}\'''')
            await self.run_sql(f'''update location set is_booked = False where location_name = \'{self.source}\'''')

            return task_id


async def set_gp(self, key_name, value):
    """
    :param self: ==self
    :param key_name: 设置的键
    :param value: 设置的值
    :return: ->bool
    """
    try:
        check_set_sql = f"select gp_id from layer4_1_om.globalparameters where gp_name=\'{key_name}\';"
        result = await execute_sql(self=self, sql=check_set_sql)
        insert_or_update_sql = ''
        if not result:
            insert_or_update_sql = f"insert into layer4_1_om.globalparameters(gp_name, gp_value, gp_value_type) values(\'{key_name}\', \'{value}\', \'str\');"
        else:
            insert_or_update_sql = f"update layer4_1_om.globalparameters set gp_value=\'{value}\' where gp_name=\'{key_name}\';"
        await execute_sql(self=self, sql=insert_or_update_sql)
        return True
    except Exception as e:
        await self.log(e)
    return False


async def get_gp(self, key_name):
    """
    :param self: ==self
    :param key_name: 查询的键
    :return: 查到的值
    """
    try:
        check_set_sql = f"select gp_value from layer4_1_om.globalparameters where gp_name=\'{key_name}\';"
        await self.log(check_set_sql)
        result = await execute_sql(self=self, sql=check_set_sql)
        await self.log(f'check_set_sql_result={result}')
        if result:
            return result[0].get('gp_value')
    except Exception as e:
        await self.log(e)
    return None


##############################以下为预留接口######################################

# 预设搜路omi
async def Route_main(self, src_name, dst_name):
    xmlfile = './docks.xml'
    self.father = []
    self.position = {}
    try:
        father = await self.get_gp('father')
        self.father = json.loads(father)
    except:
        self.father = []
    try:
        position = await self.get_gp('position')
        self.position = json.loads(position)
    except:
        self.position = {}
    if not self.father or not self.position:
        p_location = await self.run_sql('select id from location where is_leaf is false')
        for location in p_location:
            f = await self.run_sql(f'select count(*) from location_relation where location_id = {location["id"]}')
            await self.log(f'{f}++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
            if f[0]['count'] == 0:
                self.father.append(location['id'])
                location_ids = await self.get_leaf_location_ids(location['id'])
                self.position[str(location['id'])] = location_ids
        await self.set_gp('father', json.dumps(self.father), 'str')
        await self.set_gp('position', json.dumps(self.position), 'str')
    try:
        flag1 = await self.get_gp('docks')
    except:
        flag1 = None
    try:
        flag2 = await self.get_gp('rowcol')
    except:
        flag2 = None
    if flag1 is None:
        await read_docks(self, xmlfile)
    if flag2 is None:
        await init_position(self)
    route_src, route_dst = await route_cal(self, src_name, dst_name)
    self.logger.debug(f"src:{route_src},dst:{route_dst}")
    return route_src, route_dst


async def goto_load_with_scan_code(self, location, scan_type, group_id, sequence_id, taskid=None, agv_list=None,
                                   agv_id=None):
    try:
        base_url = await get_gp(self, 'base_url')
        low_battery = await get_gp(self, 'low_battery')
    except:
        self.logger.error("未查询到地址或低电量阈值配置，请配置后重试")
        base_url = None
        low_battery = None
    if group_id and sequence_id:
        flag = is_area(self, location)
        if flag:
            object = await self.run_sql(f"select * from object where object_name = \'{location}\'")
            if not object:
                return 504
        result, code, taskid = await function_main(self, base_url=base_url, scan_type=scan_type, location=location,
                                                   follow_task=True, taskid=taskid, agv_list=agv_list, agv_id=agv_id)
        return result, code, taskid
    else:
        return None, None, None


async def is_outof_area(self, location_name, x, y):
    location = await location_name2id_dock(self, location_name)
    father, position_list = await get_location_position(self, location['id'])
    if not father:
        self.logger.error("此location不属于某区域")
        return True
    around = json.loads(await self.get_gp(f'position{father}'))
    if x < (around[0] - 0.05) or x > (around[1] + 0.05) or y < (around[2] - 0.05) or y > (around[3] + 0.05):
        return True
    return False


async def is_area(self, location_name):
    xmlfile = './docks.xml'
    self.father = []
    self.position = {}
    try:
        father = await self.get_gp('father')
        self.father = json.loads(father)
    except:
        self.father = []
    try:
        position = await self.get_gp('position')
        self.position = json.loads(position)
    except:
        self.position = {}
    if not self.father or not self.position:
        p_location = await self.run_sql('select * from location where is_leaf is false')
        for location in p_location:
            f = await self.run_sql(f'select count(*) from location_relation where location_id = {location["id"]}')
            await self.log(f'{f}++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
            if f[0]['count'] == 0:
                self.father.append(location['id'])
                location_ids = await self.get_leaf_location_ids(location['id'])
                self.position[str(location['id'])] = location_ids
        await self.set_gp('father', json.dumps(self.father), 'str')
        await self.set_gp('position', json.dumps(self.position), 'str')
    try:
        flag1 = await self.get_gp('docks')
    except:
        flag1 = None
    try:
        flag2 = await self.get_gp('rowcol')
    except:
        flag2 = None
    if flag1 is None:
        await read_docks(self, xmlfile)
    if flag2 is None:
        await init_position(self)
    location_infor = await location_name2id_dock(self, location_name)
    a = await self.run_sql(f'''select * from location where id = {location_infor['id']} limit 1''')
    if a[0]['is_leaf'] is True:
        return True
    else:
        return False


async def read_docks(self, xmlfile):
    dom = xml.dom.minidom.parse(xmlfile)
    document = dom.documentElement
    docks = document.getElementsByTagName('dock')
    for dock in docks:
        xy = []
        dock_id = dock.getElementsByTagName('id')
        pos = dock.getElementsByTagName('pos')
        id = dock_id[0].firstChild.data
        pos_x = pos[0].getAttribute('x')
        pos_y = pos[0].getAttribute('y')
        xy.append(round(float(pos_x), 2))
        xy.append(round(float(pos_y), 2))
        await self.set_gp(str(id), str(xy), 'str')
    await self.set_gp('docks', '1', 'str')
    await self.ts_delay(5)


async def location_name2id_dock(self, location_name):
    self.logger.debug(location_name + 'gggggggggggggggggggggggg')
    location_row = await execute_sql(self=self,
                                     sql=f'select id,layout_dock_id from location where location_name = \'{location_name}\'')
    location_infor = {'location_name': location_name, 'id': location_row[0]['id'],
                      'dock': location_row[0]['layout_dock_id']}
    self.logger.debug(location_name + 'ppppppppppppppppppppppppp')
    return location_infor


async def get_location_position(self, location_id):
    for father in self.father:
        if location_id in self.position[str(father)]:
            return father, self.position[str(father)]
    return None, None


async def init_position(self):
    self.position_point = {}
    self.row_col = {}
    for father in self.father:
        row = []
        col = []
        p = []
        for location_id in self.position[str(father)]:
            location_p = await self.run_sql(f'''select * from location where id = {location_id} limit 1''')
            if location_p[0]['layout_dock_id']:
                xy = json.loads(await self.get_gp(str(location_p[0]['layout_dock_id'])))
                row.append(float(xy[0]))
                col.append(float(xy[1]))
        row = sorted(list(set(row)))
        col = sorted(list(set(col)))
        if len(row) != 0:
            p.append(row[0])
            p.append(row[-1])
            i = 0
            for row_l in row:
                await self.set_gp(f"{father}row{i}", str(row_l), 'str')
                i += 1
        if len(col) != 0:
            p.append(col[0])
            p.append(col[-1])
            i = 0
            for col_l in col:
                await self.set_gp(f"{father}col{i}", str(col_l), 'str')
                i += 1
        await self.set_gp(f"position{father}", str(p), 'str')
    await self.set_gp('rowcol', '1', 'str')


async def cal_weight(sxmin, sxmax, symin, symax, dxmin, dxmax, dymin, dymax, sx, sy, dx, dy):
    point_list = {}
    w1 = 2
    w2 = 1
    point_list['ul'] = (abs(symax - sy) + abs(dxmax - dx)) * w1 + (abs(dxmax - sx) + abs(symax - dy)) * w2
    point_list['uu'] = (abs(symax - sy) + abs(dymin - dy)) * w1 + (abs(symax - dymin) + abs(dx - sx)) * w2
    point_list['ud'] = (abs(symax - sy) + abs(dymax - dy)) * w1 + (abs(symax - dymax) + abs(dx - sx)) * w2
    point_list['ur'] = (abs(symax - sy) + abs(dxmin - dx)) * w1 + (abs(symax - dy) + abs(dxmin - sx)) * w2
    point_list['dl'] = (abs(symin - sy) + abs(dxmax - dx)) * w1 + (abs(symin - dy) + abs(sx - dxmax)) * w2
    point_list['du'] = (abs(symin - sy) + abs(dymin - dy)) * w1 + (abs(symin - dymin) + abs(sx - dx)) * w2
    point_list['dd'] = (abs(symin - sy) + abs(dymax - dy)) * w1 + (abs(symin - dymax) + abs(sx - dx)) * w2
    point_list['dr'] = (abs(symin - sy) + abs(dxmin - dx)) * w1 + (abs(symin - dy) + abs(dxmin - sx)) * w2
    point_list['ll'] = (abs(sxmin - sx) + abs(dxmax - dx)) * w1 + (abs(sxmin - dxmax) + abs(sy - dy)) * w2
    point_list['lu'] = (abs(sxmin - sx) + abs(dymin - dy)) * w1 + (abs(sxmin - dx) + abs(dymin - sy)) * w2
    point_list['ld'] = (abs(sxmin - sx) + abs(dymax - dy)) * w1 + (abs(sxmin - dx) + abs(dymax - sy)) * w2
    point_list['lr'] = (abs(sxmin - sx) + abs(dxmin - dx)) * w1 + (abs(sxmin - dxmin) + abs(sy - dy)) * w2
    point_list['rl'] = (abs(sxmax - sx) + abs(dxmax - dx)) * w1 + (abs(sxmax - dxmax) + abs(sy - dy)) * w2
    point_list['ru'] = (abs(sxmax - sx) + abs(dymin - dy)) * w1 + (abs(sxmax - dx) + abs(dymin - sy)) * w2
    point_list['rd'] = (abs(sxmax - sx) + abs(dymax - dy)) * w1 + (abs(sxmax - dx) + abs(dymax - sy)) * w2
    point_list['rr'] = (abs(sxmax - sx) + abs(dxmin - dx)) * w1 + (abs(sxmax - dxmin) + abs(sy - dy)) * w2
    weight_dict = sorted(point_list.items(), key=lambda x: x[1], reverse=False)
    return weight_dict


async def get_route(self, x, y, to, position, way):
    route_list = []
    is_position = await self.run_sql(f'''select location_name from location where id = {position} limit 1''')
    if 'storehouse' in is_position[0]['location_name']:
        if way == 1:
            if to == 'u' or to == 'd':
                while (1):
                    row_col = await self.run_sql(
                        f"select gp_name from layer4_1_om.globalparameters where gp_value = '{y}' and gp_name like '{position}%' limit 1")
                    if row_col:
                        break
                    await self.ts_delay(2)
                max_p = await self.get_gp(f'position{position}')
                max_p = json.loads(max_p)
                max_y = max_p[3]
                while (1):
                    max = await self.run_sql(
                        f"select * from layer4_1_om.globalparameters where gp_value = '{max_y}' and gp_name like '{position}%' limit 1")
                    if max:
                        break
                    await self.ts_delay(2)
                row = int(row_col[0]['gp_name'].split('col')[-1])
                max_num = int(max[0]['gp_name'].split('col')[-1])
                if to == 'u':
                    for i in range(row + 1):
                        y = float(await self.get_gp(f"{position}col{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_d'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_r')
                        flag3 = await get_gp(self, f'{f[0]}_l')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i += 1
                        else:
                            return None
                    return route_list
                if to == 'd':
                    i = max_num
                    while (i >= row):
                        y = float(await self.get_gp(f"{position}col{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_u'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_r')
                        flag3 = await get_gp(self, f'{f[0]}_l')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i -= 1
                        else:
                            return None
                    self.logger.error(route_list)
                    return route_list
            if to == 'l' or to == 'r':
                while (1):
                    row_col = await self.run_sql(
                        f"select * from layer4_1_om.globalparameters where gp_value = '{x}' and gp_name like '{position}%' limit 1")
                    if row_col:
                        break
                    await self.ts_delay(2)
                max_p = await self.get_gp(f'position{position}')
                max_p = json.loads(max_p)
                max_x = max_p[1]
                while (1):
                    max = await self.run_sql(
                        f"select * from layer4_1_om.globalparameters where gp_value = '{max_x}' and gp_name like '{position}%' limit 1")
                    if max:
                        break
                    await self.ts_delay(2)
                col = int(row_col[0]['gp_name'].split('row')[-1])
                max_num = int(max[0]['gp_name'].split('row')[-1])
                self.logger.debug(to + row_col[0]['gp_name'] + 'ggggggggggggggggggggg')
                if to == 'r':
                    for i in range(col + 1):
                        x = float(await self.get_gp(f"{position}row{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_l'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_u')
                        flag3 = await get_gp(self, f'{f[0]}_d')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i += 1
                        else:
                            return None
                    self.logger.debug(route_list)
                    return route_list
                if to == 'l':
                    i = max_num
                    while (i >= col):
                        x = float(await self.get_gp(f"{position}row{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_r'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_u')
                        flag3 = await get_gp(self, f'{f[0]}_d')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i -= 1
                        else:
                            return None
                    return route_list
        elif way == 2:
            if to == 'u' or to == 'd':
                while (1):
                    row_col = await self.run_sql(
                        f"select * from layer4_1_om.globalparameters where gp_value = '{y}' and gp_name like '{position}%' limit 1")
                    if row_col:
                        break
                    await self.ts_delay(2)
                max_p = await self.get_gp(f'position{position}')
                max_p = json.loads(max_p)
                max_y = max_p[3]
                max = await self.run_sql(
                    f"select * from layer4_1_om.globalparameters where gp_value = '{max_y}' and gp_name like '{position}%' limit 1")
                row = int(row_col[0]['gp_name'].split('col')[-1])
                max_num = int(max[0]['gp_name'].split('col')[-1])
                if to == 'd':
                    for i in range(row + 1):
                        y = float(await self.get_gp(f"{position}col{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_d'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_r')
                        flag3 = await get_gp(self, f'{f[0]}_l')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i += 1
                        else:
                            return None
                    return route_list
                if to == 'u':
                    i = max_num
                    while (i >= row):
                        y = float(await self.get_gp(f"{position}col{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_u'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_r')
                        flag3 = await get_gp(self, f'{f[0]}_l')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i -= 1
                        else:
                            return None
                    self.logger.error(route_list)
                    return route_list
            if to == 'l' or to == 'r':
                while (1):
                    row_col = await self.run_sql(
                        f"select * from layer4_1_om.globalparameters where gp_value = '{x}' and gp_name like '{position}%' limit 1")
                    if row_col:
                        break
                    await self.ts_delay(2)
                max_p = await self.get_gp(f'position{position}')
                max_p = json.loads(max_p)
                max_x = max_p[1]
                max = await self.run_sql(
                    f"select * from layer4_1_om.globalparameters where gp_value = '{max_x}' and gp_name like '{position}%' limit 1")
                col = int(row_col[0]['gp_name'].split('row')[-1])
                max_num = int(max[0]['gp_name'].split('row')[-1])
                self.logger.debug(to + row_col[0]['gp_name'] + 'ggggggggggggggggggggg')
                if to == 'l':
                    for i in range(col + 1):
                        x = float(await self.get_gp(f"{position}row{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_l'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_u')
                        flag3 = await get_gp(self, f'{f[0]}_d')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i += 1
                        else:
                            return None
                    self.logger.debug(route_list)
                    return route_list
                if to == 'r':
                    i = max_num
                    while (i >= col):
                        x = float(await self.get_gp(f"{position}row{i}"))
                        while (1):
                            point = await self.run_sql(
                                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
                            if point:
                                break
                            await self.ts_delay(2)
                        point = point[0]['gp_name']
                        location_type = await self.run_sql(
                            f"select * from location where layout_dock_id = {point} limit 1")

                        flag = await self.get_location_pallet_and_type(int(point))
                        await self.log('((((((((((((((((((((' + point)
                        point1 = await self.get_location_name(location_type[0]['id'])
                        point1 = f'{point1.split("_")[0]}_r'
                        await self.log('((((((((((((((((((((' + point1)
                        flag1 = await get_gp(self, f'{point1}')
                        f = point1.split('_')
                        flag2 = await get_gp(self, f'{f[0]}_u')
                        flag3 = await get_gp(self, f'{f[0]}_d')
                        if not flag1:
                            flag1 = 'none'
                        if not flag2:
                            flag2 = 'none'
                        if not flag3:
                            flag3 = 'none'
                        if (flag[0][
                                0] is None and flag1 == 'none' and flag2 == 'none' and flag3 == 'none') or self.source in point1:
                            route_dock = point
                            route_list.append(location_type[0]['id'])
                            i -= 1
                        else:
                            return None
                    return route_list
    else:
        while (1):
            point = await self.run_sql(
                f"select * from layer4_1_om.globalparameters where gp_value = \'[{x}, {y}]\' limit 1")
            if point:
                break
            await self.ts_delay(2)
        location_type = await self.run_sql(
            f"select * from location where layout_dock_id = {int(point[0]['gp_name'])} limit 1")
        route_list.append(location_type[0]['id'])
        return route_list


async def route_cal(self, src_name, dst_name):
    src_infor = await location_name2id_dock(self, src_name)
    if not src_infor['dock']:
        src_infor = await location_name2id_dock(self, f'{src_name}_u')
    dst_infor = await location_name2id_dock(self, dst_name)
    if not dst_infor['dock']:
        dst_infor = await location_name2id_dock(self, f'{dst_name}_u')
    src_position = await get_location_position(self, src_infor['id'])
    dst_position = await get_location_position(self, dst_infor['id'])
    src_xy = json.loads(await self.get_gp(str(src_infor['dock'])))
    dst_xy = json.loads(await self.get_gp(str(dst_infor['dock'])))
    sx = float(src_xy[0])
    sy = float(src_xy[1])
    dx = float(dst_xy[0])
    dy = float(dst_xy[1])
    if len(src_position[1]) == 1 and len(dst_position[1]) > 1:
        smin_x = sx
        smax_x = sx
        smin_y = sy
        smax_y = sy
        dmin_x = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[0])
        dmax_x = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[1])
        dmin_y = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[2])
        dmax_y = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[3])
    elif len(dst_position[1]) == 1 and len(src_position[1]) > 1:
        smin_x = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[0])
        smax_x = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[1])
        smin_y = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[2])
        smax_y = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[3])
        dmin_x = dx
        dmax_x = dx
        dmin_y = dy
        dmax_y = dy
    elif len(src_position[1]) > 1 and len(dst_position[1]) > 1:
        smin_x = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[0])
        smax_x = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[1])
        smin_y = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[2])
        smax_y = float(json.loads(await self.get_gp(f"position{src_position[0]}"))[3])
        dmin_x = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[0])
        dmax_x = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[1])
        dmin_y = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[2])
        dmax_y = float(json.loads(await self.get_gp(f"position{dst_position[0]}"))[3])
    else:
        print("起点与目的地都不是区域，自动结束")
        return None, None
    print(smin_x, smax_x, smin_y, smax_y, dmin_x, dmax_x, dmin_y, dmax_y, sx, sy, dx, dy)
    weight_dict = await cal_weight(smin_x, smax_x, smin_y, smax_y, dmin_x, dmax_x, dmin_y, dmax_y, sx, sy, dx, dy)
    print(weight_dict)
    for weight in weight_dict:
        a = await get_route(self, sx, sy, weight[0][0], src_position[0], 2)
        b = await get_route(self, dx, dy, weight[0][1], dst_position[0], 1)
        await self.log(weight[0])
        print(src_position[0], dst_position[0])
        print(weight[0])
        if a is None or b is None:
            continue
        else:
            route_src = []
            route_dst = []
            flag = await self.run_sql(f'''select * from location where location_name = \'{src_name}\' limit 1''')
            if flag[0]['is_leaf'] is True:
                for location in a:
                    route = await self.get_location_name(location)
                    route = route.split('_')[0]
                    route_src.append(f'{route}_{weight[0][0]}')
                    if src_name not in route:
                        if weight[0][0] == 'u':
                            route_src.append((f'{route}_d'))
                        if weight[0][0] == 'd':
                            route_src.append((f'{route}_u'))
                        if weight[0][0] == 'l':
                            route_src.append((f'{route}_r'))
                        if weight[0][0] == 'r':
                            route_src.append((f'{route}_l'))
            else:
                for location in a:
                    route = await self.get_location_name(location)
                    route_src.append(f'{route}')
            flag = await self.run_sql(f'''select is_leaf from location where location_name = \'{dst_name}\' limit 1''')
            if flag[0]['is_leaf'] is True:
                if weight[0][1] == 'u':
                    for location in b:
                        route = await self.get_location_name(location)
                        route = route.split('_')[0]
                        route_dst.append(f'{route}_d')
                        if dst_name not in route:
                            route_dst.append(f'{route}_u')
                if weight[0][1] == 'd':
                    for location in b:
                        route = await self.get_location_name(location)
                        route = route.split('_')[0]
                        route_dst.append(f'{route}_u')
                        if dst_name not in route:
                            route_dst.append(f'{route}_d')
                if weight[0][1] == 'l':
                    for location in b:
                        route = await self.get_location_name(location)
                        route = route.split('_')[0]
                        route_dst.append(f'{route}_r')
                        if dst_name not in route:
                            route_dst.append(f'{route}_l')
                if weight[0][1] == 'r':
                    for location in b:
                        route = await self.get_location_name(location)
                        route = route.split('_')[0]
                        route_dst.append(f'{route}_l')
                        if dst_name not in route:
                            route_dst.append(f'{route}_r')
            else:
                for location in b:
                    route = await self.get_location_name(location)
                    route_dst.append(f'{route}')
            if src_name in route_src[-1]:
                route_src = list(reversed(route_src))
            if dst_name in route_dst[0]:
                route_dst = list(reversed(route_dst))
            self.logger.debug(weight)
            return route_src, route_dst
    print("两个点位不是库位")
    return None, None


async def function_main(self, base_url=None, scan_type=None, location=None,
                        follow_task=False, taskid=None, agv_list=None,
                        agv_id=None, need_post=1):
    headers = {"Content-Type": "application/json"}
    await self.update_order_status("active")
    # 获取location名对应的id、dock_id
    location_infor = await location_name2id_dock(self, location)

    src_fetch_opt, src_put_opt = await self.get_location_opt(location)
    rfid_result = await self.goto_check_rfid(
        json.dumps(
            {"parameter_int4_1": location_infor['id'], "parameter_int4_2": src_fetch_opt,
             "parameter_text_1": "CargoCode-1"}),
        follow_task, agv_list, agv_id, taskid)
    if self.process_type == '2' or self.process_type == '3':
        try:
            l = location.split('_')[0]
            await self.del_pallet(f'{l}_u')
            await self.del_pallet(f'{l}_r')
            await self.del_pallet(f'{l}_d')
            await self.del_pallet(f'{l}_l')
        except Exception as e:
            self.logger.error(f"+++++++++++++{self.order.order_id} {str(e)}++++++++++++")
            self.logger.error(f"+++++++++++++{self.order.order_id} 删除托盘失败++++++++++++")
    code = rfid_result[1]['parameter_varchar200_1']
    taskid = rfid_result[0]
    await self.log(f'$$$$$$$$$$$$${taskid}$$$$$$$$$$$$$')
    if scan_type == 1 or scan_type == 3:
        if need_post != 2:
            while (1):
                self.logger.debug(
                    f'upload_QRcode+++++++++{str({"orderID": self.order.order_id, "QR_code": code, "location": self.dest})}')
                headers = {"Content-Type": "application/json"}
                fail_time = 1
                while (1):
                    try:
                        flag_dict = requests.post(f'{base_url}/upload_QRcode', data=json.dumps(
                            {"orderID": self.order.order_id, "QR_code": code, "location": self.dest}), headers=headers)
                        flag_json = json.loads(flag_dict.content)
                        break
                    except Exception as e:
                        self.logger.error(str(e))

                        await self.ts_delay(5)
                self.logger.debug(f'upload_QRcode+++++++++{str(flag_json)}')
                flag = flag_json['resultCode']
                if flag == 0:
                    break
                await self.ts_delay(10)
    await self.update_order_status("source_finished")
    return self.dest, code, taskid


async def inventory_function(self, dst, agv_list=None, agv=None, taskid=None, need_post=1):
    follow_task = False
    if not taskid:
        follow_task = True
    try:
        base_url = await self.get_gp('base_url')
    except:
        base_url = None
        self.logger.debug("base_url is None")
    dst = f'{dst}_u'
    taskid = await self.goto_location_act(dst, 1, follow_task, agv_list, agv, taskid)
    location = await location_name2id_dock(self, dst)
    rfid_result = await self.goto_check_rfid(
        json.dumps({"parameter_int4_1": location['id'], "parameter_int4_2": 1, "parameter_text_1": "CargoCode-2"},
                   ), True, agv_list, agv, taskid)
    cargo_code = rfid_result[1]['parameter_varchar200_1']
    if need_post != 2:
        headers = {"Content-Type": "application/json"}
        fail_time = 1
        while (1):
            try:
                requests.post(f'{base_url}/upload_QRcode',
                              data=json.dumps({"orderID": rfid_result[0], "QR_code": cargo_code, "location": dst}),
                              headers=headers)
                break
            except Exception as e:
                self.logger.error(str(e))

                await self.ts_delay(5)
    return rfid_result[0]


async def goto_unload_with_check_area_and_report_code(self, location, location_name_list, code, scan_type, taskid=None,
                                                      agv_list=None,
                                                      agv_id=None, need_post=1):
    while (1):
        base_url = await get_gp(self, 'base_url')
        low_battery = await get_gp(self, 'low_battery')
        src_fetch_opt, src_put_opt = await self.get_location_opt(location)
        location_infor = await location_name2id_dock(self, location)
        check_area = await self.get_mapping_value(location_infor['id'], 1)
        if check_area and self.dest_is_robot == '1':
            headers = {"Content-Type": "application/json"}
            if need_post != 2:
                response = requests.post(f'{base_url}/unloadingAllow',
                                         data=json.dumps(
                                             {"orderID": self.order.order_id, "dst": location, "sku": "abc"}),
                                         headers=headers)
                result_json = json.loads(response.content)
            else:
                result_json = {"unloadingAllow": False, "newDst": "Robot-9-3"}
            if result_json['unloadingAllow'] is True:
                taskid = await self.goto_location_act_c(location, src_put_opt, False, agv_list, agv_id, taskid)
                while (1):
                    src_xy = await self.get_agv_pos(agv_id)
                    x = round(src_xy[0], 2)
                    y = round(src_xy[1], 2)
                    a = await is_outof_area(self, f'{self.source}_u', x, y)
                    b = await self.get_task_agv(taskid)
                    if a and b:
                        break
                    await self.ts_delay(2)
                if location_name_list:
                    await release_location(self=self, location_name_list=location_name_list,
                                           lock=f'order_{self.order.order_id}')
                while (1):
                    is_finish = await self.is_task_finished(taskid)
                    if is_finish == 0:
                        io_id = await self.get_mapping_value(location_infor['id'], 4)
                        if io_id:
                            await self.ts_delay(1)
                            await self.set_ssio(io_id[0], 0, 17)
                        break
                    await self.ts_delay(5)
                break
            if result_json['newDst']:
                location = result_json['newDst']
                flag = await is_area(self, location)
                if flag:
                    new_location = f"{location}_u"
                    while (1):
                        _, dst_route_location_list = await Route_main(self, self.dest, new_location)
                        await set_logger(self=self, log_info='搜索前往卸货点库位路线成功:{}'.format(dst_route_location_list))
                        if dst_route_location_list:
                            lock_result = await lock_location(self=self, location_name_list=dst_route_location_list,
                                                              lock=f'order_{self.order.order_id}')
                            await set_logger(self=self, log_info='成功锁定卸货路线{}'.format(dst_route_location_list))
                            if lock_result:
                                # 变更路线权重
                                await reset_edge_weight(self=self, location_list=dst_route_location_list, agv_id=agv_id)
                                taskid = await self.goto_location_act_c(dst_route_location_list[-1], src_put_opt, False,
                                                                        agv_list, agv_id,
                                                                        taskid)
                                l = location.split('_')[0]
                                await self.add_pallet(f'{l}_u', 1)
                                await self.set_pallet_batch_no(f'{l}_u', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_u')
                                await self.set_pallet_location(f'{l}_u', l_infor['id'])
                                await self.add_pallet(f'{l}_r', 1)
                                await self.set_pallet_batch_no(f'{l}_r', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_r')
                                await self.set_pallet_location(f'{l}_r', l_infor['id'])
                                await self.add_pallet(f'{l}_d', 1)
                                await self.set_pallet_batch_no(f'{l}_d', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_d')
                                await self.set_pallet_location(f'{l}_d', l_infor['id'])
                                await self.add_pallet(f'{l}_l', 1)
                                await self.set_pallet_batch_no(f'{l}_l', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_l')
                                await self.set_pallet_location(f'{l}_l', l_infor['id'])
                                while (1):
                                    src_xy = await self.get_agv_pos(agv_id)
                                    x = round(src_xy[0], 2)
                                    y = round(src_xy[1], 2)
                                    a = await is_outof_area(self, f'{self.source}_u', x, y)
                                    b = await self.get_task_agv(taskid)
                                    if a and b:
                                        break
                                    await self.ts_delay(2)
                                if location_name_list:
                                    await release_location(self=self, location_name_list=location_name_list,
                                                           lock=f'order_{self.order.order_id}')
                                while (1):
                                    is_finish = await self.is_task_finished(taskid)
                                    if is_finish == 0:
                                        break
                                    await self.ts_delay(5)
                                if scan_type == 2 or scan_type == 3:
                                    if need_post != 2:
                                        headers = {"Content-Type": "application/json"}
                                        fail_time = 1
                                        while (1):
                                            try:
                                                requests.post(f'{base_url}/upload_QRcode',
                                                              data=json.dumps(
                                                                  {"orderID": self.order.order_id, "QR_code": code,
                                                                   "location": location}),
                                                              headers=headers)
                                                break
                                            except Exception as e:
                                                self.logger.error(str(e))

                                                await self.ts_delay(5)
                                return 0
                        await self.ts_delay(3)
                else:
                    await self.goto_location_act_c(result_json['newDst'], src_put_opt, False, agv_list, agv_id, taskid)
                    while (1):
                        src_xy = await self.get_agv_pos(agv_id)
                        x = round(src_xy[0], 2)
                        y = round(src_xy[1], 2)
                        a = await is_outof_area(self, f'{self.source}_u', x, y)
                        b = await self.get_task_agv(taskid)
                        if a and b:
                            break
                        await self.ts_delay(2)
                    if location_name_list:
                        await release_location(self=self, location_name_list=location_name_list,
                                               lock=f'order_{self.order.order_id}')
                    while (1):
                        is_finish = await self.is_task_finished(taskid)
                        if is_finish == 0:
                            break
                        await self.ts_delay(5)
                    if scan_type == 2:
                        if need_post != 2:
                            requests.post(f'{base_url}/upload_QRcode',
                                          {"orderID": self.order.order_id, "QR_code": code,
                                           "location": result_json['newDst']})
                    location_infor = await self.run_sql(
                        f'''select * from location where location_name = \'{result_json['newDst']}\'''')
                    io_id = await self.get_mapping_value(location_infor[0]['id'], 4)
                    if io_id:
                        await self.ts_delay(1)
                        await self.set_ssio(io_id[0], 0, 17)
                    return 0
            while (1):
                area = await self.get_put_location_by_rule([check_area[0]], 1, book=False)
                if area[0]:
                    break
                self.logger.error('have no check area!')
                await self.update_order_status('have no check area!')
                await self.ts_delay(3)
            # f = await self.get_location_pallet(i)
            # if not f:
            taskid = await self.goto_location_c(area[0], 2, True, agv_list, agv_id, taskid)
            # while(1):
            #     p = await self.run_sql(f"select * from object where object_name = '{i}'")
            #     if not p:
            #         # ret = await self.add_pallet(str(i), 1)
            #         break
            # await self.set_pallet_batch_no(str(i), '1')
            # ret = await self.set_pallet_location(str(i), i)
            while (1):
                src_xy = await self.get_agv_pos(agv_id)
                x = round(src_xy[0], 2)
                y = round(src_xy[1], 2)
                a = await is_outof_area(self, f'{self.source}_u', x, y)
                b = await self.get_task_agv(taskid)
                if a and b:
                    break
                await self.ts_delay(2)
            if location_name_list:
                await release_location(self=self, location_name_list=location_name_list,
                                       lock=f'order_{self.order.order_id}')
            await ask_can_put(self, base_url, scan_type, src_put_opt, location, low_battery, code,
                              need_post, area[0], taskid, agv_list, agv_id)
            io_id = await self.get_mapping_value(location_infor['id'], 4)
            if io_id:
                await self.ts_delay(1)
                await self.set_ssio(io_id[0], 0, 17)
            return taskid
            # else:
            #     await self.update_order_status("没有空闲的check点")
            #     continue
        else:
            taskid = await self.goto_location_act_c(location, src_put_opt, False, agv_list, agv_id, taskid)
            io_id = await self.get_mapping_value(location_infor['id'], 4)
            if self.process_type == '1' or self.process_type == '3':
                l = location.split('_')[0]
                await self.add_pallet(f'{l}_u', 1)
                await self.set_pallet_batch_no(f'{l}_u', '1')
                l_infor = await location_name2id_dock(self, f'{l}_u')
                await self.set_pallet_location(f'{l}_u', l_infor['id'])
                await self.add_pallet(f'{l}_r', 1)
                await self.set_pallet_batch_no(f'{l}_r', '1')
                l_infor = await location_name2id_dock(self, f'{l}_r')
                await self.set_pallet_location(f'{l}_r', l_infor['id'])
                await self.add_pallet(f'{l}_d', 1)
                await self.set_pallet_batch_no(f'{l}_d', '1')
                l_infor = await location_name2id_dock(self, f'{l}_d')
                await self.set_pallet_location(f'{l}_d', l_infor['id'])
                await self.add_pallet(f'{l}_l', 1)
                await self.set_pallet_batch_no(f'{l}_l', '1')
                l_infor = await location_name2id_dock(self, f'{l}_l')
                await self.set_pallet_location(f'{l}_l', l_infor['id'])
            while (1):
                is_finish = await self.is_task_finished(taskid)
                if is_finish == 0:
                    break
                await self.ts_delay(5)
            if io_id:
                await self.set_ssio(io_id[0], 0, 17)
            await self.run_sql(f'''update location set can_put = False where location_name = \'{self.dest}\'''')
            if scan_type == 2 or scan_type == 3:
                if need_post != 2:
                    headers = {"Content-Type": "application/json"}
                    fail_time = 1
                    while (1):
                        try:
                            requests.post(f'{base_url}/upload_QRcode',
                                          data=json.dumps(
                                              {"orderID": self.order.order_id, "QR_code": code, "location": location}),
                                          headers=headers)
                            break
                        except Exception as e:
                            self.logger.error(str(e))

                            await self.ts_delay(5)
            return taskid


async def ask_can_put(self, base_url, scan_type, src_put_opt, dest, low_battery, code, need_post, area_location,
                      taskid=None,
                      agv_list=None,
                      agv_id=None):
    while True:
        if need_post != 2:
            headers = {"Content-Type": "application/json"}
            fail_time = 1
            while (1):
                try:
                    response = requests.post(f'{base_url}/unloadingAllow',
                                             data=json.dumps(
                                                 {"orderID": self.order.order_id, "dst": dest, "sku": "abc"}),
                                             headers=headers)
                    break
                except Exception as e:
                    self.logger.error(str(e))

                    await self.ts_delay(5)
            result_json = json.loads(response.content)
            self.logger.info(f"ask_can_put+++++++{str(result_json)}")
        else:
            result_json = {"unloadingAllow": False, "newDst": "Robot-9-7"}
        battery = await self.get_agv_battery_percentage(agv_id)
        if result_json['unloadingAllow'] is True:
            while (1):
                src_xy = await self.get_agv_pos(agv_id)
                x = round(src_xy[0], 2)
                y = round(src_xy[1], 2)
                a = await is_outof_area(self, f'{self.source}_u', x, y)
                b = await self.get_task_agv(taskid)
                if a and b:
                    break
                await self.ts_delay(2)
            await finish_task(self, task_id=taskid)
            while (1):
                is_finish = await self.is_task_finished(taskid)
                if is_finish == 0:
                    break
                await self.ts_delay(5)
            await self.release_location(area_location)
            # await self.del_pallet(pallet)
            break
        if result_json['newDst']:
            location = result_json['newDst']
            flag = await is_area(self, location)
            if flag:
                new_location = f"{location}_u"
                while (1):
                    _, dst_route_location_list = await Route_main(self, dest, new_location)
                    await set_logger(self=self, log_info='搜索前往卸货点库位路线成功:{}'.format(dst_route_location_list))
                    if dst_route_location_list:
                        lock_result = await lock_location(self=self, location_name_list=dst_route_location_list,
                                                          lock=f'order_{self.order.order_id}')
                        await set_logger(self=self, log_info='成功锁定卸货路线{}'.format(dst_route_location_list))
                        if lock_result:
                            # 变更路线权重
                            await reset_edge_weight(self=self, location_list=dst_route_location_list, agv_id=agv_id)
                            await self.release_location(area_location)
                            taskid = await self.goto_location_act_c(dst_route_location_list[-1], src_put_opt, False,
                                                                    agv_list, agv_id,
                                                                    taskid)
                            l = location.split('_')[0]
                            await self.add_pallet(f'{l}_u', 1)
                            await self.set_pallet_batch_no(f'{l}_u', '1')
                            l_infor = await location_name2id_dock(self, f'{l}_u')
                            await self.set_pallet_location(f'{l}_u', l_infor['id'])
                            await self.add_pallet(f'{l}_r', 1)
                            await self.set_pallet_batch_no(f'{l}_r', '1')
                            l_infor = await location_name2id_dock(self, f'{l}_r')
                            await self.set_pallet_location(f'{l}_r', l_infor['id'])
                            await self.add_pallet(f'{l}_d', 1)
                            await self.set_pallet_batch_no(f'{l}_d', '1')
                            l_infor = await location_name2id_dock(self, f'{l}_d')
                            await self.set_pallet_location(f'{l}_d', l_infor['id'])
                            await self.add_pallet(f'{l}_l', 1)
                            await self.set_pallet_batch_no(f'{l}_l', '1')
                            l_infor = await location_name2id_dock(self, f'{l}_l')
                            await self.set_pallet_location(f'{l}_l', l_infor['id'])
                            while (1):
                                is_finish = await self.is_task_finished(taskid)
                                if is_finish == 0:
                                    break
                                await self.ts_delay(5)
                            if scan_type == 2 or scan_type == 3:
                                if need_post != 2:
                                    headers = {"Content-Type": "application/json"}
                                    fail_time = 1
                                    while (1):
                                        try:
                                            requests.post(f'{base_url}/upload_QRcode',
                                                          data=json.dumps(
                                                              {"orderID": self.order.order_id, "QR_code": code,
                                                               "location": location}),
                                                          headers=headers)
                                            break
                                        except Exception as e:
                                            self.logger.error(str(e))

                                            await self.ts_delay(5)
                            if lock_result:
                                await release_location(self=self, location_name_list=lock_result,
                                                       lock=f'order_{self.order.order_id}')
                            return 0
                    await self.ts_delay(3)
            else:
                while (1):
                    src_xy = await self.get_agv_pos(agv_id)
                    x = round(src_xy[0], 2)
                    y = round(src_xy[1], 2)
                    a = await is_outof_area(self, f'{self.source}_u', x, y)
                    b = await self.get_task_agv(taskid)
                    if a and b:
                        break
                    await self.ts_delay(2)
                await finish_task(self, taskid)
                while (1):
                    is_finish = await self.is_task_finished(taskid)
                    if is_finish == 0:
                        break
                    await self.ts_delay(5)
                await self.goto_location_act(result_json['newDst'], src_put_opt, False, agv_list, agv_id, taskid)
                if scan_type == 2:
                    if need_post != 2:
                        requests.post(f'{base_url}/upload_QRcode',
                                      {"orderID": self.order.order_id, "QR_code": code,
                                       "location": result_json['newDst']})
                location_infor = await self.run_sql(
                    f'''select * from location where location_name = \'{result_json['newDst']}\'''')
                io_id = await self.get_mapping_value(location_infor[0]['id'], 4)
                if io_id:
                    await self.ts_delay(1)
                    await self.set_ssio(io_id[0], 0, 17)
                return 0
        if battery <= float(low_battery):
            if need_post != 2:
                headers = {"Content-Type": "application/json"}
                fail_time = 1
                while (1):
                    try:
                        new_area_str = requests.post(f'{base_url}/api/om/order/update_location1/',
                                                     data=json.dumps({'orderId': self.order.order_id}), headers=headers)
                        new_area_json = json.loads(new_area_str.content)
                        break
                    except Exception as e:
                        self.logger.error(str(e))

                        await self.ts_delay(5)
            else:
                new_area_json = {'location': 'A1-1-1'}
            if new_area_json['location']:
                while (1):
                    src_xy = await self.get_agv_pos(agv_id)
                    x = round(src_xy[0], 2)
                    y = round(src_xy[1], 2)
                    a = await is_outof_area(self, f'{self.source}_u', x, y)
                    b = await self.get_task_agv(taskid)
                    if a and b:
                        break
                    await self.ts_delay(2)
                await finish_task(self, taskid)
                while (1):
                    is_finish = await self.is_task_finished(taskid)
                    if is_finish == 0:
                        break
                    await self.ts_delay(5)
                location = new_area_json['location']
                flag = await is_area(self, location)
                if flag:
                    new_location = f"{location}_u"
                    while (1):
                        _, dst_route_location_list = await Route_main(self, dest, new_location)
                        await set_logger(self=self, log_info='搜索前往卸货点库位路线成功:{}'.format(dst_route_location_list))
                        if dst_route_location_list:
                            lock_result = await lock_location(self=self, location_name_list=dst_route_location_list,
                                                              lock=f'order_{self.order.order_id}')
                            await set_logger(self=self, log_info='成功锁定卸货路线{}'.format(dst_route_location_list))
                            if lock_result:
                                # 变更路线权重
                                await reset_edge_weight(self=self, location_list=dst_route_location_list, agv_id=agv_id)
                                await self.release_location(area_location)
                                taskid = await self.goto_location_act_c(dst_route_location_list[-1], src_put_opt, False,
                                                                        agv_list, agv_id,
                                                                        taskid)
                                l = location.split('_')[0]
                                await self.add_pallet(f'{l}_u', 1)
                                await self.set_pallet_batch_no(f'{l}_u', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_u')
                                await self.set_pallet_location(f'{l}_u', l_infor['id'])
                                await self.add_pallet(f'{l}_r', 1)
                                await self.set_pallet_batch_no(f'{l}_r', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_r')
                                await self.set_pallet_location(f'{l}_r', l_infor['id'])
                                await self.add_pallet(f'{l}_d', 1)
                                await self.set_pallet_batch_no(f'{l}_d', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_d')
                                await self.set_pallet_location(f'{l}_d', l_infor['id'])
                                await self.add_pallet(f'{l}_l', 1)
                                await self.set_pallet_batch_no(f'{l}_l', '1')
                                l_infor = await location_name2id_dock(self, f'{l}_l')
                                await self.set_pallet_location(f'{l}_l', l_infor['id'])
                                while (1):
                                    is_finish = await self.is_task_finished(taskid)
                                    if is_finish == 0:
                                        break
                                    await self.ts_delay(5)
                                if scan_type == 2 or scan_type == 3:
                                    if need_post != 2:
                                        headers = {"Content-Type": "application/json"}
                                        fail_time = 1
                                        while (1):
                                            try:
                                                requests.post(f'{base_url}/upload_QRcode',
                                                              data=json.dumps(
                                                                  {"orderID": self.order.order_id, "QR_code": code,
                                                                   "location": location}),
                                                              headers=headers)
                                                break
                                            except Exception as e:
                                                self.logger.error(str(e))
                                                await self.ts_delay(5)
                                if lock_result:
                                    await release_location(self=self, location_name_list=lock_result,
                                                           lock=f'order_{self.order.order_id}')
                                return 0
                        await self.ts_delay(3)
                else:
                    await self.release_location(area_location)
                    await self.goto_location_act(dest, src_put_opt, False, agv_list, agv_id, taskid)
                    location_infor = await self.run_sql(
                        f'''select * from location where location_name = \'{location}\'''')
                    io_id = await self.get_mapping_value(location_infor[0]['id'], 4)
                    if io_id:
                        await self.ts_delay(1)
                        await self.set_ssio(io_id[0], 0, 17)
                    return 0
            if scan_type == 2:
                if need_post != 2:
                    headers = {"Content-Type": "application/json"}
                    fail_time = 1
                    while (1):
                        try:
                            requests.post(f'{base_url}/upload_QRcode',
                                          data=json.dumps(
                                              {"orderID": self.order.order_id, "QR_code": code, "location": dest}),
                                          headers=headers)
                            break
                        except Exception as e:
                            self.logger.error(str(e))

                            await self.ts_delay(5)
            return 0
        await self.ts_delay(5)
    await self.goto_location_act(dest, src_put_opt, False, agv_list, agv_id, taskid)
    location_infor = await self.run_sql(f'''select * from location where location_name = \'{dest}\'''')
    io_id = await self.get_mapping_value(location_infor[0]['id'], 4)
    if io_id:
        await self.ts_delay(1)
        await self.set_ssio(io_id[0], 0, 17)
    if scan_type == 2 or scan_type == 3:
        if need_post != 2:
            headers = {"Content-Type": "application/json"}
            fail_time = 1
            while (1):
                try:
                    requests.post(f'{base_url}/upload_QRcode',
                                  data=json.dumps({"orderID": self.order.order_id, "QR_code": code, "location": dest}),
                                  headers=headers)
                    break
                except Exception as e:
                    self.logger.error(str(e))

                    await self.ts_delay(5)


async def general_p2p(self, source, destination, agv_type, current_task_id=None, follow_task=False):
    """
    标准点到点
    :param self:
    :param source: 起点
    :param destination: 终点
    :param agv_type: agv类型
    :param current_task_id: 当前task id，默认为None
    :param follow_task: 后置任务，默认为False
    :return: task id
    """
    task_id = current_task_id
    # 获取起点的取货opt id
    src_fetch_opt, src_put_opt = await self.get_location_opt(source)
    # 下发起点取货任务
    task_id = await self.goto_location_act(source, src_fetch_opt, True, agv_type, None, task_id)
    await self.update_order_status('source_finished')
    if 'Robot' in source:
        agv = await self.get_task_agv(task_id)
        location_infor = await location_name2id_dock(self, source)
        dst = await self.get_mapping_value(location_infor['id'], 2)
        if dst:
            task_id = await self.goto_location_act(dst[0], 1, True, agv_list, agv, task_id)

    # 获取终点的卸货opt id
    dst_fetch_opt, dst_put_opt = await self.get_location_opt(destination)
    # 下发终点卸货任务
    task_id = await self.goto_location_act(destination, dst_put_opt, follow_task, agv_type, None, task_id)
    return task_id


async def set_logger(self, log_info):
    await self.log(
        f'#####################################Order({self.order.order_id}): {log_info}###################################')


async def execute_sql(self, sql):
    await set_logger(self=self, log_info=f'sql={sql}')
    result = await self.run_sql(sql)
    await set_logger(self=self, log_info=f'result={result}')
    return result
