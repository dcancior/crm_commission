{
    'name': 'CRM Commission',
    'version': '16.0.1.0.0',
    'summary': 'Permite asignar comisión a los vendedores del CRM',
    'depends': ['crm','sale'],
    'data': [
        'views/crm_team_views.xml',
        'views/commission_report_wizard_view.xml',
        'security/ir.model.access.csv',
        'views/commission_report_pdf.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_inherit.xml',
    ],
    'installable': True,
}