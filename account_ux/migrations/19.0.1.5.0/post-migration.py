import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Update account.journal_comp_rule domain_force
    even if the rule is marked as noupdate.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    rule = env.ref("account.journal_comp_rule", raise_if_not_found=False)
    if not rule:
        _logger.info("account_ux post-migrate 19.0.1.5.0: journal_comp_rule no encontrada, skip")
        return
    new_domain = """[
        '|',
        ('company_id', 'in', company_ids),
        '&',
        ('company_id', 'parent_of', company_ids),
        ('shared_to_branches', '=', True)
    ]"""
    # write ignora noupdate
    rule.write(
        {
            "domain_force": new_domain,
        }
    )
    _logger.info("account_ux post-migrate 19.0.1.5.0: journal_comp_rule domain_force actualizado")