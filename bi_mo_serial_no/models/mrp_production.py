# -*- coding: utf-8 -*-
# Part of Browseinfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import float_compare, float_round

class MrpProduction(models.Model):
	""" Manufacturing Orders """
	_inherit = 'mrp.production'
	_description = 'Production Order'

	producing_quantity = fields.Float(string="Quantity Producing", digits='Product Unit of Measure', default=0)
	is_producing_qty = fields.Boolean(string="Is Producing", default=False)
	is_workorder = fields.Boolean(string="Is workorder",compute="compute_work_order")
	
	def open_produce_product(self):
		self.ensure_one()
		if self.bom_id.type == 'phantom':
			raise UserError(_('You cannot produce a MO with a bom kit product.'))
		action = self.sudo().env.ref('bi_mo_serial_no.act_mrp_product_produce_view').read()[0]
		return action

	def compute_work_order(self):
		if self.workorder_ids:
			self.is_workorder = False
		else:
			self.is_workorder = True