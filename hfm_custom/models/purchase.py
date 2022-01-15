# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurhcaseOrder(models.Model):
    _inherit = 'purchase.order'

    challan_no = fields.Char()
    challan_date = fields.Date()