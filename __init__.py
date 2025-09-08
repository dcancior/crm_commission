# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

try:
    import odoo.http as ohttp

    if hasattr(ohttp, "__wz_get_response"):
        _orig_wz_get_response = ohttp.__wz_get_response  # guarda la función original (2 args)

        def _bridge_get_response(self, environ=None, scope=None):
            # ignoramos 'scope' y delegamos al ORIGINAL
            return _orig_wz_get_response(self, environ)

        ohttp.__wz_get_response = _bridge_get_response
except Exception:
    # no bloquear el arranque si algo falla
    pass

from . import models
from . import wizards