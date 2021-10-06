# -*- coding: utf-8 -*-
# Part of Browseinfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import float_compare, float_round
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from datetime import datetime
from dateutil.relativedelta import relativedelta



class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    use_next_on_work_order_id = fields.Many2one('mrp.workorder',
        string="Next Work Order to Use",
        help='Technical: used to figure out default serial number on work orders')


class Company(models.Model):
    _inherit = 'res.company'


    serial_no = fields.Integer(default = 0)
    digits_serial_no = fields.Integer(string='Digits :')
    prefix_serial_no = fields.Char(string="Prefix :")

class ProductProductInherit(models.Model):
    _inherit = "product.template"

    digits_serial_no = fields.Integer(string='Digits :')
    prefix_serial_no = fields.Char(string="Prefix :")

class MrpProductionInherit(models.Model):
    """ Manufacturing Orders """
    _inherit = 'mrp.production'

    mrp_production_qty = fields.Float(string="MRP Production Quantity",default=0)

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        result = super(MrpProductionInherit, self).copy(default)
        for wo in result.workorder_ids:
            wo.workorder_qty = 0
        return result

    def create_all_qty(self):
        count = self.product_qty
        if len(self.workorder_ids) == 0:
            raise UserError(_('There is no work order for this product'))
        for wo in self.workorder_ids:
            wo.button_start()
            for i in range(int(count)):
                wo.button_finish()

    @api.model
    def create(self, values):
            
        res = super(MrpProductionInherit,self).create(values)
        if res.lot_producing_id:
            pass
        else:
            company = self.env.company
            result = self.env['res.config.settings'].sudo().search([],order="id desc", limit=1)
            product = self.env['product.product'].search([('id','=',values.get('product_id'))])

            if result.apply_method == "global":
                digit = result.digits_serial_no
                prefix = result.prefix_serial_no
            else:
                digit = product.digits_serial_no
                prefix = product.prefix_serial_no
                
            serial_no = company.serial_no + 1
            serial_no_digit=len(str(company.serial_no))

            diffrence = abs(serial_no_digit - digit)
            if diffrence > 0:
                no = "0"
                for i in range(diffrence-1) :
                    no = no + "0"
            else :
                no = ""

            if prefix != False:
                lot_no = prefix+no+str(serial_no)
            else:
                lot_no = str(serial_no)
            company.sudo().update({'serial_no' : serial_no})
            lot_serial_no = self.env['stock.production.lot'].create({'name' : lot_no,'product_id':product.id,'company_id': company.id})
            res.update({'lot_producing_id':lot_serial_no.id})
        return res

    def _workorders_create(self, bom, bom_data):
        res = super(MrpProductionInherit, self)._workorders_create(bom,bom_data)
        if self.product_id.tracking == 'serial' :
            lot_id_list = []
            for i in range(0,int(self.product_qty)) :
                lot_id = self.create_custom_lot_no(res[0])
                lot_id_list.append(lot_id.id)
            res[0].finished_lot_id = lot_id_list[0]
        elif self.product_id.tracking == 'lot' :
            lot_id = self.create_custom_lot_no(res[0])
            for lot in res:
                lot.finished_lot_id = lot_id.id
        return res

class MrpWorkorder(models.Model):
    """ Manufacturing Orders """
    _inherit = 'mrp.workorder'

    workorder_qty = fields.Float(string="workorder Quantity")

    def _assign_default_final_lot_id(self):
        lot_id_list = self.env['stock.production.lot'].search([('use_next_on_work_order_id', '=', self.id)],
                                                                    order='create_date, id')
        finished_lot = []
        for line in self.finished_workorder_line_ids :
            finished_lot.append(line.lot_id.id)
        for lot in lot_id_list :
            if lot.id in finished_lot :
                continue
            else :
                self.finished_lot_id = lot
                break
        
    def record_production(self):
        res = super(MrpWorkorder, self).record_production()
        if self.qty_produced == self.qty_production :
            for line in self.finished_workorder_line_ids :
                if self.production_id.product_id.tracking == 'serial':
                    line.lot_id.use_next_on_work_order_id = self.next_work_order_id.id
            return res
        if self.production_id.product_id.tracking == 'serial':
            self._assign_default_final_lot_id()
        return res

    def create_all_qty(self):
        """ to create all qty using batch serial number """
        count = self.qty_producing
        for i in range(int(count)):
            self.button_start()

    def button_start(self):
        self.ensure_one()
        # As button_start is automatically called in the new view
        if self.state in ('done', 'cancel'):
            return True

        if self.product_tracking == 'serial':
            self.qty_producing = 1.0
        else:
            self.qty_producing = self.qty_remaining

        self.env['mrp.workcenter.productivity'].create(
            self._prepare_timeline_vals(self.duration, datetime.now())
        )
        if self.production_id.state != 'progress':
            self.production_id.write({
                'date_start': datetime.now(),
            })
        if self.state == 'progress':
            return True
        start_date = datetime.now()
        vals = {
            'state': 'progress',
            'date_start': start_date,
        }
        if self.production_id.mrp_production_qty == 0:
            self.production_id.write({'mrp_production_qty':1})
            for lines in self.production_id.move_raw_ids:
                if lines.product_id.tracking == 'serial':
                    stock_move_line = self.env['stock.move.line'].search([('reference','=',self.production_id.name),('qty_done','=',0),('product_id','=',lines.product_id.id)],limit=lines.should_consume_qty)
                    for move_lines in stock_move_line:
                        if move_lines.product_id.tracking == 'serial':
                            move_lines.write({'qty_done':1})
                if lines.product_id.tracking == 'lot':
                    stock_move_line = self.env['stock.move.line'].search([('reference','=',self.production_id.name),('product_id','=',lines.product_id.id)])
                    for move_lines in stock_move_line:
                        move_lines.write({'qty_done':lines.should_consume_qty})
        if not self.leave_id:
            leave = self.env['resource.calendar.leaves'].create({
                'name': self.display_name,
                'calendar_id': self.workcenter_id.resource_calendar_id.id,
                'date_from': start_date,
                'date_to': start_date + relativedelta(minutes=self.duration_expected),
                'resource_id': self.workcenter_id.resource_id.id,
                'time_type': 'other'
            })
            vals['leave_id'] = leave.id
            return self.write(vals)
        else:
            if self.date_planned_start > start_date:
                vals['date_planned_start'] = start_date
            if self.date_planned_finished and self.date_planned_finished < start_date:
                vals['date_planned_finished'] = start_date
            return self.write(vals)


    def _update_finished_move(self):
        """ Update the finished move & move lines in order to set the finished
        product lot on it as well as the produced quantity. This method get the
        information either from the last workorder or from the Produce wizard."""
        if self.production_id.product_id.tracking == 'serial':
            for workorders in self.production_id.workorder_ids:
                workorder_id = workorders
            if workorder_id.id == self.id:
                company = self.env.company
                result = self.env['res.config.settings'].sudo().search([],order="id desc", limit=1)

                if result.apply_method == "global":
                    digit = result.digits_serial_no
                    prefix = result.prefix_serial_no
                else:
                    digit = self.product_id.digits_serial_no
                    prefix = self.product_id.prefix_serial_no

                serial_no = company.serial_no + 1
                serial_no_digit=len(str(company.serial_no))


                diffrence = abs(serial_no_digit - digit)
                if diffrence > 0:
                    no = "0"
                    for i in range(diffrence-1) :
                        no = no + "0"
                else :
                    no = ""

                if prefix != False:
                    lot_no = prefix+no+str(serial_no)
                else:
                    lot_no = str(serial_no)
                lot_id = self.production_id.lot_producing_id
                company.sudo().update({'serial_no' : serial_no})
                lot_serial_no = self.env['stock.production.lot'].sudo().create({'name' : lot_no,'product_id':self.product_id.id,'company_id': self.env.company.id})
            production_move = self.production_id.move_finished_ids.filtered(
                lambda move: move.product_id == self.product_id and
                move.state not in ('done', 'cancel')
            )
            if not production_move:
                return
            if production_move.product_id.tracking != 'none':
                if not self.finished_lot_id:
                    self.finished_lot_id= lot_serial_no
                    raise UserError(_('You need to provide a lot for the finished product.'))
                move_line = production_move.move_line_ids.filtered(
                    lambda line: line.lot_id.id == self.finished_lot_id.id
                )
                if move_line:
                    if self.product_id.tracking == 'serial':
                        raise UserError(_('You cannot produce the same serial number twice.'))
                    move_line.product_uom_qty += self.qty_producing
                    move_line.qty_done += self.qty_producing
                else:
                    location_dest_id = production_move.location_dest_id._get_putaway_strategy(self.product_id).id or production_move.location_dest_id.id
                    if workorder_id.id == self.id:
                        move_line.sudo().create({
                            'move_id': production_move.id,
                            'product_id': production_move.product_id.id,
                            'lot_id': lot_serial_no.id,
                            'product_uom_qty': self.qty_producing,
                            'product_uom_id': self.product_uom_id.id,
                            'qty_done': 1,
                            'location_id': production_move.location_id.id,
                            'location_dest_id': location_dest_id,
                        })
            else:
                rounding = production_move.product_uom.rounding
                production_move._set_quantity_done(
                    float_round(self.qty_producing, precision_rounding=rounding)
                )
        else:
            res = super(MrpWorkorder, self)._update_finished_move()
            return res


    def button_finish(self):
        end_date = datetime.now()
        for workorder in self:
            if workorder.production_id.product_id.tracking == 'serial':
                workorder.workorder_qty +=1
                if workorder.production_id.qty_producing != workorder.production_id.product_qty:
                    if self.production_id.finished_move_line_ids:
                        workorder.production_id.write({'qty_producing':workorder.production_id.qty_producing+1,})
                    workorder._update_finished_move()
                if self.production_id.qty_producing == self.production_id.product_qty:
                    for lines in workorder.production_id.move_raw_ids:
                        lines.write({'quantity_done':lines.should_consume_qty})
                        if lines.product_id.tracking == 'serial':
                            stock_move_line = self.env['stock.move.line'].search([('reference','=',self.production_id.name),('qty_done','=',0)])
                            for move_lines in stock_move_line:
                                if move_lines.product_id.tracking == 'serial':
                                    move_lines.write({'qty_done':1})
                        if lines.product_id.tracking == 'lot':
                            stock_move_line = self.env['stock.move.line'].search([('reference','=',self.production_id.name),('product_id','=',lines.product_id.id)])
                            for move_lines in stock_move_line:
                                move_lines.write({'qty_done':lines.should_consume_qty})

                if workorder.workorder_qty == self.production_id.product_qty:
                    if workorder.state in ('done', 'cancel'):
                        continue
                    workorder.end_all()
                    vals = {
                        'qty_produced': workorder.qty_produced or workorder.qty_producing or workorder.qty_production,
                        'state': 'done',
                        'date_finished': end_date,
                        'date_planned_finished': end_date
                    }
                    if not workorder.date_start:
                        vals['date_start'] = end_date
                    if not workorder.date_planned_start or end_date < workorder.date_planned_start:
                        vals['date_planned_start'] = end_date
                    workorder.write(vals)

                    workorder._start_nextworkorder()
                    return True
            else:
                res = super(MrpWorkorder, self).button_finish()
                return res



        

   
