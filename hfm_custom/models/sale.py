# -*- coding: utf-8 -*-

from odoo import models, fields, api



class SaleOrder(models.Model):
    _inherit = 'sale.order'

    challan_no = fields.Char()
    challan_date = fields.Date()