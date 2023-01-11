from ts_template.ts_template import CancelException
from ts_template.ts_template import StopException
from pathlib import Path
import time

desc = '项目描述'
para_template = {'p2a_lista_new': {'src': 'str', 'dst_area': 'str', 'pallet_type': 'int'}}
operator_list = []


async def run(self):
    self.global_location_locked = []
    try:
        # 加锁保证多车联动
        await require_lock_location(self=self, location_name='start_order')
        self.global_location_locked.append('start_order')
        task_id, agv_id = await self.goto_location_reserve(self.src, True, [4, 802], None, None)

        # TODO:agv库位托盘检查，需确认是否可以这么做
        await agv_pallet_check(self=self, agv_id=agv_id)

        # 选择存放库位
        location_name = await get_unload_location(self=self, area_name=self.dst_area, pallet_type=self.pallet_type)
        # 在起始点添加托盘
        add_status = await add_pallet_to_location(self=self, location=self.src, pallet_type=self.pallet_type)
        if not add_status:
            return 0
        # 开始搬运
        task_id = await self.goto_location_load(self.src, True, [4, 802], agv_id, task_id)
        # await require_release_location(self=self, location_name='start_order')
        task_id = await self.goto_location_unload(location_name, True, [4, 802], agv_id, task_id)
        # 搬运空托回原位置
        # 空托计数
        count = await get_empty_pallet_count(self=self)
        # 获取取空托位
        empty_pallet_location = 'Laser Empty {}'.format(count)
        empty_pallet_location_fetch, empty_pallet_location_put = await self.get_location_opt(empty_pallet_location)
        count = await get_empty_pallet_count(self=self)
        task_id = await self.goto_location_act('Laser Empty {}'.format(count), empty_pallet_location_fetch, True, [4, 802],
                                               agv_id, task_id)
        task_id = await self.goto_location_act(self.src, 1, False, [4, 802], agv_id, task_id)
        await reset_empty_pallet_count(self=self, count=count)
        for location in self.global_location_locked:
            await require_release_location(self=self, location_name=location)
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await self.cancel()
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        await agv_pallet_delete(self)
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        return 504


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    #     pallet_id_1 = """select o.object_name  from layer2_pallet.object_location ol
    # left join layer2_pallet."location" l on l.id = ol.current_location_id
    # left join layer2_pallet."object" o on o.id = ol.object_id
    # where l.location_name ='RV1-1';"""
    #     result_1 = await self.run_sql(pallet_id_1)
    #     if result_1:
    #         await self.del_pallet(result_1[0]['object_name'])
    #         self.logger.info(f"""###########车辆一对应托盘已删除：{result_1[0]['object_name']}""")
    #     pallet_id_2 = """select o.object_name  from layer2_pallet.object_location ol
    # left join layer2_pallet."location" l on l.id = ol.current_location_id
    # left join layer2_pallet."object" o on o.id = ol.object_id
    # where l.location_name ='RV2-1';"""
    #     result_2 = await self.run_sql(pallet_id_2)
    #     if result_2:
    #         await self.del_pallet(result_1[0]['object_name'])
    #         self.logger.info(f"""###########车辆二对应托盘已删除：{result_1[0]['object_name']}""")
    await agv_pallet_delete(self)
    await self.cancel_task()
    for location in self.global_location_locked:
        await require_release_location(self=self, location_name=location)
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(self.order.order_id))
    return


async def add_pallet_to_location(self, location, pallet_type):
    pallet_id = await self.add_pallet('pallet{}'.format(time.time_ns()), pallet_type)
    if pallet_id < 0:
        return False
    await self.set_pallet_status(pallet_id, 1)
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
                                                  logger_info=f'Target{location_name}has been locked by order{location_lock_order_id},would fetching continuously!')
            else:
                await set_order_status_and_logger(self=self, logger_info='active')
                return False
        else:
            await set_order_status_and_logger(self=self, logger_info=f'Target has been locked:{location_name}')
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
        if not location_lock_order_id:
            return
        if str(location_lock_order_id) != str(self.order.order_id):
            await set_order_status_and_logger(self=self, logger_info=f'Lock Released：{location_name}')
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
        result = await self.run_sql(check_set_sql)
        await self.log(f'check_set_sql_result={result}')
        if result:
            return result[0].get('gp_value')
    except Exception as e:
        await self.log(e)
    return None


async def logger(self, logger_info):
    await self.log(f'Order({self.order.order_id}):****************************{logger_info}********************************')


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


async def agv_pallet_check(self, agv_id: int):
    self.agv_location_name = f"RV{agv_id}-1"
    while 1:
        pallet_name = await self.get_location_pallet(self.agv_location_name)
        if not pallet_name:
            return
        self.update_order_status("Need to remove the pallet")
        self.ts_delay(3)


async def agv_pallet_delete(self):
    while 1:
        pallet_id = f"""select o.object_name  from layer2_pallet.object_location ol
        left join layer2_pallet."location" l on l.id = ol.current_location_id
        left join layer2_pallet."object" o on o.id = ol.object_id 
        where l.location_name =\'{self.agv_location_name}\';"""
        result = await self.run_sql(pallet_id)
        if not result:
            return
        await self.del_pallet(result[0]['object_name'])
        self.logger.info(f"""###########Pallet has been deleted：{result[0]['object_name']}""")
        self.ts_delay(0.5)
