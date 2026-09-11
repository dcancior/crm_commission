# -*- coding: utf-8 -*-
"""Respeta el porcentaje que cada servicio ya tenía capturado.

En esta versión el porcentaje del mecánico deja de resolverse con el truco de
"0 significa que hereda": ahora cada servicio dice explícitamente si sigue al
porcentaje general o usa uno propio (mechanic_percent_source). Hacía falta
porque un 0 puede ser deliberado —trabajos que el taller paga a un mecánico
externo y no comisionan a los internos— y antes no había forma de distinguirlo
de "todavía no lo configuro".

La columna nueva nace en 'general' para todos. Aquí se corrige a 'propio' en
los servicios que YA tenían un porcentaje capturado, que es justo el que
estaban aplicando: sin esto pasarían a seguir al general y se les cambiaría la
comisión sin que nadie lo pidiera.

Los que estaban en 0 se quedan en 'general', que es el comportamiento con el
que venían de la versión anterior.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('product_template')")
    if not cr.fetchone()[0]:
        return

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'product_template'
          AND column_name IN ('mechanic_percent_source', 'porcentaje_comision_mecanico')
    """)
    if len(cr.fetchall()) < 2:
        return

    cr.execute("""
        UPDATE product_template
        SET mechanic_percent_source = 'propio'
        WHERE COALESCE(porcentaje_comision_mecanico, 0) != 0
    """)
