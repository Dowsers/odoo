# -*- coding: utf-8 -*-
{
    'name': 'Local AI (Ollama)',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'AI features served by an Ollama server of the company network, reached through Tailscale only',
    'description': """
Local AI (Ollama)
=================
Connects Odoo to an Ollama server of the company network. Nothing is sent
outside: by default the server must be reached through Tailscale (its
address must resolve into the Tailscale ranges 100.64.0.0/10 or
fd7a:115c:a1e0::/48), otherwise the request is not sent.

* settings: address of the Ollama server, model, timeout, connection test;
* text editor: "Translate with AI" and a writing assistant (correct,
  rephrase, shorten, develop the selection; "/AI" command to write a text
  from an instruction), answered by the local server;
* chatter: "Translate" action on messages, answered by the local server
  when no Google Translate key is configured;
* a processing queue (local.ai.queue.mixin) run by a scheduled action, used
  by the other local AI modules for long jobs.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail', 'html_editor', 'web_local_only'],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'local_ai/static/src/editor/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
