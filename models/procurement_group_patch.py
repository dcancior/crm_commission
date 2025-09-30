# crm_commission/models/procurement_group_patch.py
from odoo import models

class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    def run(self, procurements, *args, **kwargs):
        # Sanitiza valores antes del super().run() (blindaje global)
        for p in procurements:
            vals = p.values

            wh = vals.get('warehouse_id')
            if isinstance(wh, int):
                vals['warehouse_id'] = self.env['stock.warehouse'].browse(wh)

            ppack = vals.get('product_packaging_id')
            if isinstance(ppack, int):
                vals['product_packaging_id'] = self.env['product.packaging'].browse(ppack)

            routes = vals.get('route_ids')
            if routes:
                route_ids = []
                for r in routes if isinstance(routes, (list, tuple)) else [routes]:
                    if hasattr(r, 'id'):
                        route_ids.append(r.id)
                    elif isinstance(r, int):
                        route_ids.append(r)
                if route_ids:
                    vals['route_ids'] = self.env['stock.route'].browse(route_ids)

        # ¡OJO! Mantén kwargs como raise_user_error para no romper la llamada del core.
        return super().run(procurements, *args, **kwargs)
