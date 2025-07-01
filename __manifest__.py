{
    'name': 'CRM Commission',
    'version': '16.0.1.0.0',
    'summary': 'Permite asignar comisión a los vendedores del CRM',
    'depends': ['crm'],
    'data': [
        'views/crm_team_views.xml',
        'views/commission_report_wizard_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
}