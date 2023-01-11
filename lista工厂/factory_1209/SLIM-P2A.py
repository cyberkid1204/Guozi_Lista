from ts_template.ts_template import CancelException
from ts_template.ts_template import StopException
from pathlib import Path

desc = '项目描述'
para_template = {'SLIM-P2A': {'PickUp': 'str', 'DropOff': 'str'}}
operator_list = []
agv_type = [i for i in range(800, 810)]


async def run(self):
    self.pallet_name = None
    self.unload_location_name = None
    try:
        # 订单锁（需要打开设置）
        # await require_execute_permission(self, lock="CurrentOrder")
        task_id, agv_id = await self.goto_location_reserve(self.PickUp, True, [4, 802], None, None)
        await agv_pallet_check(self=self, agv_id=agv_id)
        while True:
            # self.get_location_pallet_and_type:获取目标位置的当前托盘name和托盘类型name
            location_pallet_detail = await self.get_location_pallet_and_type(self.PickUp)
            # location_pallet_name, location_pallet_type = await self.get_location_pallet_and_type(self.PickUp)
            if location_pallet_detail[0][1]:
                break
            await self.update_order_status(f'No pallet on location {self.PickUp}')
            await self.ts_delay(1)
        location_pallet_type = location_pallet_detail[0][1]
        location_pallet_name = location_pallet_detail[0][0]
        self.pallet_name = location_pallet_name

        # 查询库区内是否存在位置，不存在则阻塞
        self.unload_location_name = await get_unload_location(self=self, area_name=self.DropOff,
                                                              pallet_type=location_pallet_type)
        task_id = await self.goto_location_load(self.PickUp, True, agv_type, agv_id, task_id)
        task_id = await self.goto_location_unload(self.unload_location_name, False, agv_type, agv_id, task_id)
        # await remove_execute_permission(self, lock="CurrentOrder")
        return 0
    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(self.order.order_id, Path(__file__).name))
        await cancel(self)
        # cancel逻辑处理必须在此代码之后
        return 1
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(self.order.order_id, Path(__file__).name))
        await agv_pallet_delete(self)
        if self.unload_location_name:
            await self.release_location(self.unload_location_name)
        await self.release_location(self.PickUp)
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(self.order.order_id, Path(__file__).name, e))
        return 504


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(self.order.order_id, Path(__file__).name))
    await agv_pallet_delete(self)
    if self.unload_location_name:
        await self.release_location(self.unload_location_name)
    await self.release_location(self.PickUp)
    await self.cancel_task()
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


# 订单锁
async def require_execute_permission(self, lock: str, block: bool = True):
    while 1:
        gp_value = await get_gp(self=self, lock=lock)
        if not gp_value:
            await set_gp(self, order_id=self.order.order_id, lock=lock)
            continue
        if str(gp_value) != str(self.order.order_id):
            if block:
                await set_order_status_and_logger(self=self,
                                                  logger_info=f'Waiting pre-order be done,would fetching continuously!')
            else:
                await set_order_status_and_logger(self=self, logger_info='active')
                return False
        else:
            await set_order_status_and_logger(self=self, logger_info=f'Executing')
            return True
        await self.ts_delay(0.5)


# 释放订单锁
async def remove_execute_permission(self, lock: str):
    while 1:
        gp_value = await get_gp(self=self, lock=lock)
        if not gp_value:
            return
        if str(gp_value) != str(self.order.order_id):
            await set_order_status_and_logger(self=self, logger_info=f'Order({self.order.order_id}): Lock Released')
            return
        else:
            await delete_gp_record(self=self, lock=lock, value=self.order.order_id)
        await self.ts_delay(0.5)


async def get_gp(self, lock: str):
    query_sql = f"select gp_value from layer4_1_om.globalparameters where gp_name=\'{lock}\' limit 1;"
    try:
        res = await self.run_sql(query_sql)
        if res:
            await self.log(f'query_sql_result={res}')
            return res[0].get('gp_value')
        else:
            return
    except ConnectionError as e:
        await self.log(f"数据查询异常：{str(e)}")
    return False


async def set_gp(self, order_id, lock):
    insert_sql = f"insert into layer4_1_om.globalparameters(gp_name, gp_value, gp_value_type) values(\'{lock}\', \'{order_id}\', \'str\');"
    try:
        await self.run_sql(insert_sql)
        return True
    except ConnectionError as e:
        await self.log(f"数据插入异常：{str(e)}")
    return False


async def delete_gp_record(self, lock: str, value):
    sql = f"delete from layer4_1_om.globalparameters where gp_name=\'{lock}\' and gp_value=\'{value}\';"
    await logger(self=self, logger_info="删除订单锁")
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


async def logger(self, logger_info):
    await self.log(f'Order({self.order.order_id}):****************************{logger_info}********************************')


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
        await self.log(f"""###########Pallet has been deleted：{result[0]['object_name']}""")
        self.ts_delay(0.5)
