# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Reportes de comisión de periodos extensos, generados en segundo plano.

Cuando el usuario pide en el "Reporte de Comisión de Ventas" un periodo más
grande que REPORT_MAX_RANGE_DAYS días (más de un trimestre), no se
consulta en pantalla: se crea una solicitud aquí y un cron la procesa cuando
el servidor no está ocupado, de una en una. El PDF se envía al correo del
usuario que la pidió.
"""

import base64
import logging
import os
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models

from .commission_report_wizard import COMMISSION_PAYMENT_TERM_MONTHS

_logger = logging.getLogger(__name__)

# El servidor se considera ocupado si la carga promedio del último minuto
# supera este factor por número de CPUs. Entonces el cron espera a la
# siguiente vuelta, salvo que la solicitud más antigua ya lleve
# REQUEST_MAX_WAIT_MINUTES esperando (para que nunca se quede sin enviarse).
BUSY_LOAD_FACTOR = 0.8
REQUEST_MAX_WAIT_MINUTES = 60
# Solicitudes que se procesan como máximo en cada vuelta del cron
REQUESTS_PER_RUN = 3

FILTER_PAYMENT_LABELS = {
    'all': 'Todas',
    'paid': 'Pagadas',
    'unpaid': 'No pagadas (pendientes de pagar)',
    'not_payable': 'No pagaderas',
}


class CommissionReportRequest(models.Model):
    _name = 'commission.report.request'
    _description = 'Reporte de comisión enviado por correo'
    _order = 'id desc'

    name = fields.Char(string='Reporte', compute='_compute_name', store=True)
    requested_by_id = fields.Many2one('res.users', string='Solicitó', required=True, readonly=True,
                                      default=lambda self: self.env.user)
    email_to = fields.Char(string='Enviar a', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, readonly=True,
                                 default=lambda self: self.env.company)

    # Lo que el usuario seleccionó en el reporte
    salesperson_id = fields.Many2one('res.users', string='Vendedor', required=True, readonly=True)
    date_start = fields.Date(string='Desde', required=True, readonly=True)
    date_end = fields.Date(string='Hasta', required=True, readonly=True)
    filter_payment = fields.Selection(list(FILTER_PAYMENT_LABELS.items()),
                                      string='Filtro pago comisión', default='all', readonly=True)
    sort_field = fields.Char(readonly=True)
    sort_direction = fields.Char(readonly=True)

    state = fields.Selection([
        ('pending', 'En espera'),
        ('processing', 'Generando'),
        ('done', 'Enviado'),
        ('error', 'Error'),
    ], string='Estado', default='pending', required=True, readonly=True, index=True)
    date_done = fields.Datetime(string='Enviado el', readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string='PDF', readonly=True)
    error_message = fields.Text(string='Error', readonly=True)

    @api.depends('salesperson_id', 'date_start', 'date_end')
    def _compute_name(self):
        for req in self:
            req.name = (f"{req.salesperson_id.name or ''} · "
                        f"{req.date_start and req.date_start.strftime('%d/%m/%Y') or ''} - "
                        f"{req.date_end and req.date_end.strftime('%d/%m/%Y') or ''}")

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        # Pide al cron que pase pronto; si el servidor está ocupado, él esperará
        self.env.ref('crm_commission.ir_cron_commission_report_requests').sudo()._trigger()
        return requests

    # ----------------- Cron -----------------

    @api.model
    def _server_busy(self):
        try:
            load_1min = os.getloadavg()[0]
        except (OSError, AttributeError):
            return False
        return load_1min > (os.cpu_count() or 1) * BUSY_LOAD_FACTOR

    @api.model
    def _cron_process_requests(self):
        """Procesa las solicitudes pendientes de una en una, solo si el servidor
        no está ocupado (o si la más antigua ya esperó demasiado)."""
        now = fields.Datetime.now()
        # Solicitudes que quedaron "Generando" por un reinicio del servidor
        self.search([
            ('state', '=', 'processing'),
            ('write_date', '<', now - timedelta(hours=1)),
        ]).write({'state': 'pending'})

        pending = self.search([('state', '=', 'pending')], order='id', limit=REQUESTS_PER_RUN)
        for req in pending:
            waited_too_long = req.create_date < now - timedelta(minutes=REQUEST_MAX_WAIT_MINUTES)
            if self._server_busy() and not waited_too_long:
                _logger.info("Reportes de comisión: servidor ocupado, se reintenta en la siguiente vuelta")
                return
            req._process()
            # Cada solicitud queda guardada aunque falle la siguiente
            self.env.cr.commit()

    def _process(self):
        self.ensure_one()
        self.write({'state': 'processing'})
        self.env.cr.commit()
        try:
            with self.env.cr.savepoint():
                self._generate_and_send()
            self.write({'state': 'done', 'date_done': fields.Datetime.now(), 'error_message': False})
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Reportes de comisión: no se pudo generar la solicitud %s", self.id)
            self.write({'state': 'error', 'error_message': str(exc)})
            try:
                with self.env.cr.savepoint():
                    self._send_mail(self._error_mail_body(), subject_prefix='No se pudo generar tu')
            except Exception:  # pylint: disable=broad-except
                _logger.exception("Reportes de comisión: tampoco se pudo avisar del error (%s)", self.id)

    # ----------------- Generación -----------------

    def _user_env_model(self, model_name):
        """Modelo en el entorno del usuario que pidió el reporte: mismos
        permisos, zona horaria e idioma que si lo consultara él."""
        user = self.requested_by_id
        return self.env[model_name].with_user(user).with_company(self.company_id).with_context(
            tz=user.tz or 'America/Mexico_City', lang=user.lang or 'es_MX')

    def _generate_and_send(self):
        self.ensure_one()
        wizard = self._user_env_model('commission.report.wizard').create({
            'user_id': self.salesperson_id.id,
            'period_mode': 'range',
            'quarter': False,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'filter_payment': self.filter_payment,
            'sort_field': self.sort_field or 'invoice_date',
            'sort_direction': self.sort_direction or 'asc',
        })
        pdf_bytes, data = wizard._build_report_pdf()

        attachment = self.env['ir.attachment']
        if pdf_bytes:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': wizard._report_filename(),
                'type': 'binary',
                'datas': base64.b64encode(pdf_bytes),
                'mimetype': 'application/pdf',
                'res_model': self._name,
                'res_id': self.id,
            })
            self.attachment_id = attachment
        mail = self._send_mail(self._report_mail_body(data, bool(pdf_bytes)), attachment)
        # Si se envió bien, Odoo ya lo borró (auto_delete); si sigue y falló, es error
        if mail.exists() and mail.state == 'exception':
            raise ValueError(f"No se pudo enviar el correo: {mail.failure_reason or ''}")

    def _send_mail(self, body, attachment=None, subject_prefix='Tu'):
        period = f"{self.date_start.strftime('%d/%m/%Y')} al {self.date_end.strftime('%d/%m/%Y')}"
        mail = self.env['mail.mail'].sudo().create({
            'subject': f"{subject_prefix} Reporte de Comisión de Ventas: {self.salesperson_id.name} ({period})",
            'email_from': (self.env['ir.mail_server'].sudo()._get_default_from_address()
                           or self.company_id.email_formatted),
            'email_to': self.email_to,
            'body_html': body,
            'attachment_ids': [(4, attachment.id)] if attachment else [],
            'auto_delete': True,
        })
        mail.send(raise_exception=False)
        return mail

    # ----------------- Correo -----------------

    def _requested_at_str(self):
        stamp = fields.Datetime.context_timestamp(
            self.with_context(tz=self.requested_by_id.tz or 'America/Mexico_City'), self.create_date)
        return stamp.strftime('%d/%m/%Y a las %H:%M')

    def _selection_rows(self):
        return [
            ('Vendedor', self.salesperson_id.name),
            ('Periodo', f"Del {self.date_start.strftime('%d/%m/%Y')} al {self.date_end.strftime('%d/%m/%Y')}"),
            ('Filtro de pago de comisión', FILTER_PAYMENT_LABELS.get(self.filter_payment, 'Todas')),
            ('Solicitado el', self._requested_at_str()),
        ]

    @staticmethod
    def _rows_html(rows, highlight_last=False):
        html = Markup('')
        for i, (label, value) in enumerate(rows):
            strong = highlight_last and i == len(rows) - 1
            html += Markup(
                '<tr>'
                '<td style="padding:8px 12px;color:#5b6472;font-size:14px;border-bottom:1px solid #eef0f3;'
                'width:48%;">{label}</td>'
                '<td style="padding:8px 12px;color:#1f2937;font-size:14px;border-bottom:1px solid #eef0f3;'
                '{weight}">{value}</td>'
                '</tr>'
            ).format(label=escape(label), value=escape(value),
                     weight=Markup('font-weight:700;font-size:16px;color:#14532d;') if strong else '')
        return html

    def _section_html(self, title, rows, highlight_last=False):
        return Markup(
            '<h3 style="margin:24px 0 8px;font-size:15px;color:#1f3a5f;text-transform:uppercase;'
            'letter-spacing:.04em;">{title}</h3>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;background:#ffffff;border:1px solid #eef0f3;border-radius:6px;">'
            '{rows}</table>'
        ).format(title=escape(title), rows=self._rows_html(rows, highlight_last))

    def _mail_layout(self, intro, content):
        company = self.company_id
        return Markup(
            '<div style="margin:0;padding:24px 12px;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;'
            'border:1px solid #e3e7ed;">'
            '<tr><td style="background:#1f3a5f;padding:20px 24px;">'
            '<div style="color:#c9d6e8;font-size:12px;letter-spacing:.06em;text-transform:uppercase;">{company}</div>'
            '<div style="color:#ffffff;font-size:20px;font-weight:700;margin-top:4px;">Reporte de Comisión de Ventas</div>'
            '</td></tr>'
            '<tr><td style="padding:24px;">'
            '<p style="margin:0 0 12px;font-size:15px;color:#1f2937;">Hola, {name}:</p>'
            '{intro}{content}'
            '</td></tr>'
            '<tr><td style="padding:16px 24px;background:#f8fafc;border-top:1px solid #eef0f3;'
            'font-size:12px;color:#6b7280;">'
            'Este correo se envió automáticamente desde Odoo de {company} porque solicitaste este reporte. '
            'No es necesario responder.'
            '</td></tr>'
            '</table></div>'
        ).format(company=escape(company.name), name=escape(self.requested_by_id.name),
                 intro=intro, content=content)

    def _report_mail_body(self, data, has_pdf):
        p = Markup('<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#374151;">{}</p>')
        intro = p.format(
            "Tu reporte ya está listo. Como abarca un periodo extenso, lo generamos en segundo plano "
            "en el servidor para no afectar el trabajo de los demás usuarios.")
        if has_pdf:
            intro += p.format("El detalle completo de cada factura viene en el PDF adjunto a este correo.")
        else:
            intro += p.format(
                "No se encontraron facturas con lo que seleccionaste, por eso este correo no trae PDF.")

        content = self._section_html('Lo que seleccionaste', self._selection_rows())
        if has_pdf:
            result_rows = [('Facturas en el reporte', str(data['invoice_count']))]
            if data['not_payable_count']:
                result_rows.append((
                    'Comisiones no pagaderas (no suman al total)',
                    f"{data['not_payable_count']} factura(s) · {data['commission_not_payable_total_str']}"))
            if data['manual_count']:
                result_rows.append(('Habilitadas manualmente para pago', f"{data['manual_count']} factura(s)"))
            result_rows += [
                ('Porcentaje de comisión del equipo', f"{data['commission_percent_str']} %"),
                ('Total de ventas (base comisionable)', data['amount_total_str']),
                ('Total de comisión a pagar', data['commission_total_str']),
            ]
            content += self._section_html('Lo que muestra el reporte', result_rows, highlight_last=True)
            content += Markup(
                '<p style="margin:16px 0 0;padding:12px;background:#fff8e6;border-left:4px solid #f0b429;'
                'font-size:13px;line-height:1.5;color:#5c4a12;">'
                'Solo es pagadera la comisión de las facturas que el cliente pagó al 100%% dentro de '
                '%s meses desde la fecha de factura. Las demás aparecen en el PDF con su motivo.</p>'
                % COMMISSION_PAYMENT_TERM_MONTHS)
        return self._mail_layout(intro, content)

    def _error_mail_body(self):
        intro = Markup(
            '<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#374151;">'
            'Lo sentimos, no pudimos generar tu reporte. Puedes intentarlo de nuevo desde Odoo; '
            'si vuelve a fallar, avisa a tu administrador de sistemas.</p>')
        return self._mail_layout(intro, self._section_html('Lo que seleccionaste', self._selection_rows()))
