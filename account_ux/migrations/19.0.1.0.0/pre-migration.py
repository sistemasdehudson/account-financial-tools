import logging
import json
import re

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración account_ux 19.0.1.0.0
    Elimina campo payment_method_description del arch_db de
    view_account_payment_tree_personalization.
    El campo fue eliminado en v19 pero puede quedar en arch_db desde v17.
    """
    _logger.info("account_ux pre-migrate: limpiando payment_method_description")
    cr.execute("""
        SELECT id, arch_db FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_ux'
              AND name = 'view_account_payment_tree_personalization'
              AND model = 'ir.ui.view'
        )
        AND arch_db::text LIKE '%payment_method_description%'
    """)
    row = cr.fetchone()
    if row:
        view_id, arch_db = row
        arch_dict = dict(arch_db)
        modified = False
        for lang in arch_dict:
            if 'payment_method_description' in arch_dict[lang]:
                arch_dict[lang] = re.sub(
                    r'<field[^>]*name="payment_method_description"[^>]*/>',
                    '', arch_dict[lang]
                )
                modified = True
        if modified:
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                [json.dumps(arch_dict), view_id]
            )
            _logger.info(f"  ✓ view_account_payment_tree_personalization corregida (id {view_id})")
    else:
        _logger.info("  - view_account_payment_tree_personalization ya está limpia")