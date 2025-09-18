# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

{
    'name': 'CRM Commission',
    'version': '16.0.1.0.0',
    'summary': 'Permite asignar comisión a los vendedores del CRM',
    'depends': ['crm','sale','hr'],
    'data': [
        'security/mechanic_commission_groups.xml',
        'security/ir.model.access.csv',
        
        'reports/mechanic_commission_report.xml',
        'wizards/mechanic_commission_wizard_view.xml',
        'views/crm_team_views.xml',
        'views/commission_report_wizard_view.xml',
        'views/commission_report_pdf.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_inherit.xml',
        'views/product_views.xml',
        'views/sale_views.xml',
        'views/sale_order_set_mechanic_wizard_views.xml',
        'views/assets.xml',
        
        
    ],
    'assets': {
        'web.assets_backend': [
            'crm_commission/static/src/css/mechanic_highlight.css',
            # 'crm_commission/static/src/js/mechanic_notify.js',
        ],
    },
    'installable': True,
}