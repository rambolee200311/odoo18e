import json
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
class OutboundOrderStatusHoymilesLimit(models.Model):
    _inherit = 'world.depot.outbound.order'

    status_to_confirmed_click_time=fields.Datetime(string='Status to Confirmed Click Time', copy=False, index=True)
    status_to_pick_finished_click_time=fields.Datetime(string='Status to Pick Finished Click Time', copy=False, index=True)
    outbound_pack_sync_click_time=fields.Datetime(string='Outbound Pack Sync Click Time', copy=False, index=True)
    logistics_info_sync_click_time=fields.Datetime(string='Logistics Info Sync Click Time', copy=False, index=True)
    outbound_result_sync_click_time=fields.Datetime(string='Outbound Result Sync Click Time', copy=False, index=True)

    def get_hoymiles_success_log(self, request_source, ws_op_order_no):
        for order in self:
            if not order.reference or not ws_op_order_no:
                continue
            log_env = order.env['hoymiles.api.logs'].sudo()
            log_list = log_env.search([('request_source', '=', request_source), ('request_data', 'ilike', order.reference or ''),('request_data', 'ilike', ws_op_order_no), ('response_data', 'ilike', 'failed')], order='id desc', limit=20)
            for log in log_list:
                try:
                    request_data = json.loads(log.request_data or '{}')
                    response_data = json.loads(log.response_data or '{}')
                except Exception:
                    continue
                #if request_data.get('reference') == order.reference and response_data.get('failed') is False:
                if request_data.get('reference') == order.reference and request_data.get(
                        'wsOpOrderNo') == ws_op_order_no and response_data.get('failed') is False:
                    return log
        return False

    def check_hoymiles_click_time(self, click_time_field, lock_key):
        for order in self:
            now_time = fields.Datetime.now()
            order.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s, %s)", [order.id, lock_key])
            if not order.env.cr.fetchone()[0]:
                raise UserError("正在回传，请勿重复点击。")
            order.invalidate_recordset([click_time_field])
            limit_time = order[click_time_field] + timedelta(minutes=1) if order[click_time_field] else False
            if limit_time and limit_time > now_time:
                wait_seconds = int((limit_time - now_time).total_seconds())
                raise UserError(f"请勿重复点击，{wait_seconds} 秒后再试。")
            order.write({click_time_field: now_time})
        return True

    # 拣货出库sn提前检查是否验证, 因为要传sn, 过去
    def check_hoymiles_outbound_pack_sn(self):
        for order in self:
            order_sudo = order.sudo()
            if not order_sudo.picking_PICK:
                raise UserError("请先生成拣货出库单。")
            if order_sudo.picking_PICK.state != 'done':
                raise UserError("拣货出库单未验证，不能回传 SN。")

            serial_line_list = order_sudo.outbound_order_product_ids.filtered(
                lambda line: line.product_id.tracking == 'serial')
            if not serial_line_list:
                continue

            move_env = order.env['stock.move'].sudo()
            move_list = move_env.search(
                [('picking_id.outbound_order_id', '=', order.id), ('picking_id.state', '=', 'done'),
                 ('product_id.tracking', '=', 'serial')])
            if not move_list:
                raise UserError("拣货出库单没有找到已验证的 SN 产品移动明细。")

            for move in move_list:
                rounding = move.product_uom.rounding or move.product_id.uom_id.rounding or 1.0
                serial_name_list = []
                for move_line in move.move_line_ids:
                    qty = move_line.quantity or 0.0
                    if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
                        continue
                    serial_name = move_line.lot_id.name or ''
                    if not serial_name:
                        raise UserError("产品 %s 存在未填写 SN 的拣货明细。" % move.product_id.display_name)
                    if float_compare(qty, 1.0, precision_rounding=rounding) != 0:
                        raise UserError("产品 %s 是 SN 产品，每个 SN 明细数量必须是 1。" % move.product_id.display_name)
                    serial_name_list.append(serial_name)

                move_qty = move.product_uom_qty
                if float_compare(move_qty, len(serial_name_list), precision_rounding=rounding) != 0:
                    raise UserError("产品 %s SN 数量和拣货数量不一致，拣货数量：%s，SN 数量：%s。" % (
                    move.product_id.display_name, move_qty, len(serial_name_list)))
                if len(serial_name_list) != len(set(serial_name_list)):
                    raise UserError("产品 %s 存在重复 SN，请检查后再回传。" % move.product_id.display_name)


    # 出库结果回传,提前检查数量是否一致
    def check_hoymiles_outbound_result_quantity(self):
        for order in self:
            order_sudo = order.sudo()
            picking_env = order.env['stock.picking'].sudo()
            product_env = order.env['product.product'].sudo()

            pick_list = picking_env.search([('outbound_order_id', '=', order.id), ('state', '!=', 'cancel')])
            if not pick_list:
                raise UserError("未找到拣货出库单，不能回传出库结果。")

            # not_done_pick_list = pick_list.filtered(lambda picking: picking.state != 'done')
            # if not_done_pick_list:
            #     raise UserError("拣货出库单 %s 未验证，不能回传出库结果。" % ', '.join(not_done_pick_list.mapped('name')))

            outbound_list = picking_env.browse()
            for pick in pick_list:
                current_outbound_list = picking_env.search([
                    ('origin', '=', pick.name),
                    ('picking_type_code', '=', 'outgoing'),
                    ('state', '!=', 'cancel'),
                ])
                if not current_outbound_list:
                    current_outbound_list = pick.move_ids.move_dest_ids.picking_id.filtered(
                        lambda picking: picking.picking_type_code == 'outgoing' and picking.state != 'cancel'
                    )
                if not current_outbound_list:
                    current_outbound_list = picking_env.search([
                        ('picking_type_code', '=', 'outgoing'),
                        ('state', '!=', 'cancel'),
                        ('move_ids.move_orig_ids.picking_id', '=', pick.id),
                    ])
                outbound_list |= current_outbound_list
            if not outbound_list:
                raise UserError("未找到关联的出库交货单，不能回传出库结果。")


            expect_qty_dict = {}
            actual_qty_dict = {}

            for line in order_sudo.outbound_order_product_ids:
                if not line.product_id:
                    continue
                product_id = line.product_id.id
                expect_qty_dict[product_id] = expect_qty_dict.get(product_id, 0.0) + (line.quantity or 0.0)

            for move in outbound_list.move_ids.filtered(lambda move: move.state != 'cancel' and move.product_id):
                product_id = move.product_id.id
                qty = move.quantity or 0.0
                if move.product_uom and move.product_id.uom_id:
                    qty = move.product_uom._compute_quantity(qty, move.product_id.uom_id)
                actual_qty_dict[product_id] = actual_qty_dict.get(product_id, 0.0) + qty

            error_list = []
            for product_id in set(expect_qty_dict) | set(actual_qty_dict):
                product = product_env.browse(product_id)
                rounding = product.uom_id.rounding or 1.0
                expect_qty = expect_qty_dict.get(product_id, 0.0)
                actual_qty = actual_qty_dict.get(product_id, 0.0)
                if float_compare(expect_qty, actual_qty, precision_rounding=rounding) != 0:
                    error_list.append("%s：订单数量 %s，实际出库数量 %s" % (product.display_name, expect_qty, actual_qty))

            if error_list:
                raise UserError("出库结果回传数量不一致：\n%s" % "\n".join(error_list))

    def action_set_status_to_confirmed(self):
        for order in self:
            if order.project and (order.project.name or '').lower() == 'hoymiles':
                if order.set_status_to_confirmed:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': 'Start Operation 已回传成功，请勿重复回传。', 'type': 'warning', 'sticky': False}}
                success_log = order.get_hoymiles_success_log('Outbound Order Start Operation', order.billno or '')
                if success_log:
                    order.write({'set_status_to_confirmed': True, 'set_status_to_confirmed_time': success_log.request_time or fields.Datetime.now(), 'status_to_confirmed_error_msg': False})
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': '已根据成功日志修正 Start Operation 状态，请勿重复回传。', 'type': 'success', 'sticky': False,'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},}}
                order.check_hoymiles_click_time('status_to_confirmed_click_time', 180101)
        return super().action_set_status_to_confirmed()

    def action_set_status_to_pick_finished(self):
        for order in self:
            if order.project and (order.project.name or '').lower() == 'hoymiles':
                if order.set_status_to_pick_finished:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': 'Pick Finished 已回传成功，请勿重复回传。', 'type': 'warning', 'sticky': False}}
                success_log = order.get_hoymiles_success_log('Outbound Order Pick Finished', order.billno or '')
                if success_log:
                    order.write({'set_status_to_pick_finished': True, 'set_status_to_pick_finished_time': success_log.request_time or fields.Datetime.now(), 'status_to_pick_finished_error_msg': False})
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': '已根据成功日志修正 Pick Finished 状态，请勿重复回传。', 'type': 'success', 'sticky': False,'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},}}
                order.check_hoymiles_click_time('status_to_pick_finished_click_time', 180102)
        return super().action_set_status_to_pick_finished()

    def action_set_outbound_pack_sync(self):
        for order in self:
            if order.project and (order.project.name or '').lower() == 'hoymiles':
                if order.set_outbound_pack_sync:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': 'Outbound Pack 已回传成功，请勿重复回传。', 'type': 'warning', 'sticky': False}}
                success_log = order.get_hoymiles_success_log('Outbound Pack', order.sudo().picking_PICK.name if order.sudo().picking_PICK else '')
                if success_log:
                    order.write({'set_outbound_pack_sync': True, 'set_outbound_pack_sync_time': success_log.request_time or fields.Datetime.now(), 'outbound_pack_sync_error_msg': False})
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': '已根据成功日志修正 Outbound Pack 状态，请勿重复回传。', 'type': 'success', 'sticky': False,'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},}}
                pack_list = order.sudo().outbound_order_pack_ids
                if not pack_list:
                    raise UserError("请先维护打包信息。")
                order.check_hoymiles_outbound_pack_sn()

                order.check_hoymiles_click_time('outbound_pack_sync_click_time', 180103)
        return super().action_set_outbound_pack_sync()

    def action_set_logistics_info_sync(self):
        for order in self:
            if order.project and (order.project.name or '').lower() == 'hoymiles':
                if order.set_logistics_info_sync:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': 'Logistics Info 已回传成功，请勿重复回传。', 'type': 'warning', 'sticky': False,'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},}}
                success_log = order.get_hoymiles_success_log('Logistics Info', order.billno or '')
                if success_log:
                    order.write({'set_logistics_info_sync': True, 'set_logistics_info_sync_time': success_log.request_time or fields.Datetime.now(), 'logistics_info_sync_error_msg': False})
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': '已根据成功日志修正 Logistics Info 状态，请勿重复回传。', 'type': 'success', 'sticky': False}}
                order.check_hoymiles_click_time('logistics_info_sync_click_time', 180104)
        return super().action_set_logistics_info_sync()

    def action_set_outbound_result_sync(self):
        for order in self:
            if order.project and (order.project.name or '').lower() == 'hoymiles':
                if order.set_outbound_result_sync:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': 'Outbound Result 已回传成功，请勿重复回传。', 'type': 'warning', 'sticky': False}}

                picking_env = order.env['stock.picking'].sudo()
                pick_list = picking_env.search([('outbound_order_id', '=', order.id), ('state', '=', 'done')])
                outbound_list = picking_env.browse()

                for pick in pick_list:
                    current_outbound_list = picking_env.search(
                        [('origin', '=', pick.name), ('picking_type_code', '=', 'outgoing'), ('state', '!=', 'cancel')])
                    if not current_outbound_list:
                        current_outbound_list = pick.move_ids.move_dest_ids.picking_id.filtered(
                            lambda picking: picking.picking_type_code == 'outgoing' and picking.state != 'cancel'
                        )
                    if not current_outbound_list:
                        current_outbound_list = picking_env.search([
                            ('picking_type_code', '=', 'outgoing'),
                            ('state', '!=', 'cancel'),
                            ('move_ids.move_orig_ids.picking_id', '=', pick.id),
                        ])
                    outbound_list |= current_outbound_list

                outbound_result_ws_op_order_no = outbound_list[0].name if outbound_list else ''
                success_log = order.get_hoymiles_success_log('Outbound Result', outbound_result_ws_op_order_no)

                if success_log:
                    order.write({'set_outbound_result_sync': True, 'set_outbound_result_sync_time': success_log.request_time or fields.Datetime.now(), 'outbound_result_sync_error_msg': False})
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '提示', 'message': '已根据成功日志修正 Outbound Result 状态，请勿重复回传。', 'type': 'success', 'sticky': False,'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},}}

                order.check_hoymiles_outbound_result_quantity()

                order.check_hoymiles_click_time('outbound_result_sync_click_time', 180105)
        return super().action_set_outbound_result_sync()