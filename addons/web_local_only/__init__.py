# -*- coding: utf-8 -*-
import re

from . import controllers
from . import models

# Static links to odoo.com in e-mail templates, e.g. "Powered by <a href="https://www.odoo.com?...">Odoo</a>":
# the anchor is removed, its text is kept.
# The address may contain the other kind of quote, e.g. t-attf-href="https://www.odoo.com?x={{ ctx.get('y') }}".
ODOO_COM_ANCHOR = re.compile(
    r'<a\b[^>]*\b(?:t-attf-)?href=(["\'])https?://(?:www\.)?odoo\.com(?:(?!\1).)*\1[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL)


def strip_odoo_com_links(env):
    """Remove the links to odoo.com from the e-mail templates, in every language."""
    languages = [code for code, _name in env['res.lang'].get_installed()]
    templates = env['mail.template'].sudo().with_context(active_test=False).search([])
    changed = 0
    for template in templates:
        for lang in languages:
            record = template.with_context(lang=lang)
            body = record.body_html or ''
            cleaned = ODOO_COM_ANCHOR.sub(r'\2', body)
            if cleaned != body:
                record.body_html = cleaned
                changed += 1
    return changed


def disable_lead_enrichment(env):
    """CRM: no automatic lead enrichment, which sends the e-mail domains of the
    new leads to Odoo's IAP service (same as "Enrich leads on demand only" in
    the CRM settings)."""
    cron = env.ref('crm_iap_enrich.ir_cron_lead_enrichment', raise_if_not_found=False)
    if cron:
        cron.sudo().active = False
        env['ir.config_parameter'].sudo().set_param('crm.iap.lead.enrich.setting', 'manual')


def post_init_hook(env):
    strip_odoo_com_links(env)
    disable_lead_enrichment(env)
