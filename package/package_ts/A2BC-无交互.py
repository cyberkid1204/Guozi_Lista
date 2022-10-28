import json
import requests
import datetime
from pathlib import Path
from ts_template.ts_template import CancelException
from ts_template.ts_template import StopException

desc = 'p2p_template'
para_template = {'p2p_template': {'source': 'str', 'dest': 'str'}}
operator_list = []
agv_type = [4]
request_body = {"orderID": "",
                "orderName": "",
                "orderStatus": "dropoff_finish1",
                "agvIDList": "4",
                "priority": 1,
                "currentDes": "",
                "currentCmd": "",
                "errorCode": 0,
                "extraInfo1": "",
                "extraInfo2": "",
                "deadLine": "",
                "createdTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }


async def run(self):
    status = 0
    try:
        # fetch order extra parameters(which sent by wms to create new order)
        source_details = eval(self.source)
        src_location = source_details.get('location')  # "A"
        src_number = source_details.get('number')
        src_sku = source_details.get('sku')

        extra_details = "{{\"location\":\"{}\",\"number\":{},\"sku\":\"{}\"}}"

        # fetching pickup's check points
        source_check_name = await self.get_mapping_value(src_location, 1)
        self.logger.info(f'1111111source_check_name:{source_check_name}')
        task_id = None
        if source_check_name:
            # navigating to check point and updating order status
            task_id = await self.goto_location_act(source_check_name[0], -1, True, agv_type)

            self.logger.info('Already finished pickup informing'.center(20, '*'))

        # fetch start point's opt and make a new pick up task
        fetch_opt, put_opt = await self.get_location_opt(src_location)
        task_id = await self.goto_location_act(src_location, fetch_opt, True, agv_type, None, task_id)

        self.logger.info('Already finished pickup'.center(20, '#'))

        # 判断dest
        dest_location_details = eval(self.dest)  # [{}{}]
        follow_task = True
        unloading_times = 1
        destination = None
        diff_num = None
        while 1:
            if diff_num == 0:
                break
            # for number, dest_location_info in enumerate(dest_location_details):
            dest_location = dest_location_details[0].get('location')
            # if wms_pick_finish_response.get('newDst') is not None:
            #     dest_location = wms_pick_finish_response.get('newDst')

            dest_drop_amounts = dest_location_details[0].get('number')

            # fetch pick up point's opt
            pickup_checkpoint = await self.get_mapping_value(dest_location, 1)
            if not pickup_checkpoint:
                await self.set_order_error("src:{} wasn't configure check point".format(dest_location))
                self.logger.info("src:{} wasn't configure check point".format(dest_location))
                return 0

            nav_opt, nav_drop_opt = await self.get_location_opt(pickup_checkpoint[0])

            # if number == len(dest_location_details) - 1:
            #     follow_task = False
            if not destination:
                # if len(dest_location_details) == 1:
                nav_opt = -1

            # According the amounts of pickup and drop calculate drop's dock point
            diff_num = src_number - dest_drop_amounts
            self.logger.info("source_sku_num: {}, dest_sku_num: {}, diff_num: {}!"
                             .format(src_number, dest_drop_amounts, diff_num))

            if diff_num > 0:
                dock_location = await self.get_gp("{}_2".format(dest_location))
                src_number -= dest_drop_amounts
            elif diff_num == 0:
                dock_location = await self.get_gp("{}_4".format(dest_location))
                src_number -= dest_drop_amounts
            else:
                await self.set_order_error("The quantity of pickup is less than that of discharge!")
                self.logger.info("The quantity of pickup is less than that of discharge!")
                return 0

            task_id = await self.goto_location_act(pickup_checkpoint[0], nav_opt, True, agv_type, None, task_id)

            # task_id = await check_location_empty(self, dock_location, pickup_checkpoint[1], task_id)
            task_id = await self.goto_location_act(pickup_checkpoint[1], -1, True, agv_type, None, task_id)

            await self.ts_delay(5)
            # 卸货前通知订单号、卸几列、sku
            await self.update_order_status_with_extra_info("inform_dropoff{}".format(unloading_times),
                                                           extra_details.format(dock_location,
                                                                                dest_drop_amounts,
                                                                                src_sku))
            # await update_request_body(self, request_body, status='inform_dropoff{}'.format(unloading_times),
            #                           extra_info=extra_details.format(dock_location, dest_drop_amounts, src_sku))
            #
            # wms_drop_response = await update_order_status(self, data=request_body)
            # if wms_drop_response.get('nextDst') is not None:
                # dock_location = wms_drop_response.get('nextDst')
            # fetch drop point's opt_id
            fetch_opt, put_opt = await self.get_location_opt(dock_location)
            task_id = await self.goto_location_act(dock_location, put_opt, follow_task, agv_type, None, task_id)
            # 卸货前通知订单号、卸几列、sku
            # await self.update_order_status_with_extra_info("dropoff_finish{}".format(unloading_times), "")
            # await update_request_body(self, request_body, status="dropoff_finish{}".format(unloading_times))
            # while diff_num != 0:
            #     wms_drop_response = await update_order_status(self, data=request_body)
            #     if wms_drop_response.get('nextDst') is not None:
            #         dock_location = wms_drop_response.get('nextDst')
            #         break
            #     else:
            #         self.ts_delay(2)
            #         continue
            # else:
            #     await update_order_status(self, data=request_body)
            self.logger.info('Already finished drop'.center(20, '*'))
            # 通知整体完成
            # await update_request_body(self, request_body, status="finish".format(unloading_times))
            # # base_url/orderStatusReport
            # await update_order_status(self, data=request_body)
            # self.logger.info('Order{} finished'.format(request_body.get('orderID')).center(20,'*')
            await self.ts_delay(3)
            unloading_times += 1
            destination = dock_location

    except CancelException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get cancel command'.format(
                self.order.order_id, Path(__file__).name))
        status = 1
        await self.cancel()
        return status
    except StopException as e:
        self.logger.info(
            'Order:{} When run file \"{}\", get stop ts command'.format(
                self.order.order_id, Path(__file__).name))
        return 2
    except Exception as e:
        self.logger.error(
            'Order({}) When run file \"{}\", get exception：{}'.format(
                self.order.order_id, Path(__file__).name, e))
        return 504
    self.logger.info(
        'Order:{} Run file \"{}\", finished!'.format(self.order.order_id,
                                                     Path(__file__).name))
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(
            self.order.order_id))
    return status


async def cancel(self):
    self.logger.info('Order:{} When run file {}, run cancel operation'.format(
        self.order.order_id, Path(__file__).name))
    # User define code

    # User define code
    self.logger.debug(
        '============================== Order:{} Done==============================\n'.format(
            self.order.order_id))
    return


async def check_location_empty(self, location_name, buffer_location, current_task_id=None):
    task_id = current_task_id
    # fetch io id
    location_io_id_list = await self.get_mapping_value(location_name, 2)
    if location_io_id_list:
        do_id = location_io_id_list[0]
        di_id = location_io_id_list[1]
        nav_flag = True
        while True:
            await self.set_ssio(do_id, 0, 100)
            di_value = self.get_ssio(di_id, 0)
            if di_value != 101:
                if nav_flag:
                    task_id = self.goto_location_act(buffer_location, -1, True, agv_type, None, task_id)
                    nav_flag = False
                await self.ts_delay(1)
                continue
            # if di == 101
            await self.set_ssio(do_id, 0, 0)
            await self.poll_ssio(do_id, 0, 0)
            await self.set_ssio(di_id, 0, 0)
            await self.poll_ssio(di_id, 0, 0)
            break
    return task_id


async def update_order_status(self, data):
    while True:
        try:
            # requests_url = await self.get_gp('report_url')
            requests_url = "http://10.20.181.40:7777/api/map/query"
            requests_data = json.dumps(data)
            headers = {"User-Agent": "PostmanRuntime/7.29.2","Content-Type": "application/json"}
            response = requests.post(requests_url, requests_data,headers=headers)
            if response.status_code != 200:
                await self.ts_delay(1)
                continue
            else:
                response_dict = json.loads(response.text)
            return response_dict

        except Exception as e:
            self.logger.info(str(e))
            await self.ts_delay(1)


async def update_request_body(self, body, status, extra_info=None):
    source_details = eval(self.source)
    fetch_order_info = await self.get_order_info()
    order_info = json.loads(fetch_order_info)
    body['orderName'] = source_details.get('order_name')
    body['priority'] = source_details.get('priority')
    body['orderID'] = order_info.get('order_id')
    body['orderStatus'] = status
    body['extraInfo1'] = extra_info
