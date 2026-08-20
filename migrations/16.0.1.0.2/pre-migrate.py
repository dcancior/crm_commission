# -*- coding: utf-8 -*-
"""
Antes de esta versión, la restricción unique(user_id, year, month, company_id)
de sale.commission.goal no llegó a aplicarse en la base de datos porque ya
existían filas duplicadas (creadas cuando la lista era editable en línea) y
Postgres rechazó el ALTER TABLE en silencio. Aquí limpiamos esas duplicadas
ANTES de que Odoo vuelva a intentar crear la restricción, para que esta vez
sí quede activa.

Nos quedamos con la fila de mayor id (la más reciente) por cada combinación
de vendedor/año/mes/compañía y eliminamos el resto.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('sale_commission_goal')")
    if not cr.fetchone()[0]:
        return

    cr.execute("""
        DELETE FROM sale_commission_goal a
        USING sale_commission_goal b
        WHERE a.user_id = b.user_id
          AND a.year = b.year
          AND a.month = b.month
          AND a.company_id = b.company_id
          AND a.id < b.id
    """)
