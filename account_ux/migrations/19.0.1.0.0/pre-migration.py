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
              AND name IN ('view_account_payment_tree', 'view_account_payment_tree_personalization')
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

    # Limpiar use_search_filter_amount del arch_db
    _logger.info("account_ux pre-migrate: limpiando use_search_filter_amount")
    cr.execute("""
        UPDATE ir_ui_view
        SET arch_db = CAST(
            regexp_replace(
                arch_db::text,
                '<setting id=\"use_search_filter_amount\"[^<]*(<[^/][^>]*>[^<]*</[^>]*>|<[^/][^>]*/?>)*[^<]*</setting>',
                '',
                'g'
            ) AS jsonb
        )
        WHERE arch_db::text LIKE '%use_search_filter_amount%'
    """)
    _logger.info(f"  ✓ {cr.rowcount} vistas con use_search_filter_amount limpiadas")

    # Marcar módulos desinstalados intencionalmente como uninstalled
    # para evitar error de inconsistent states en el proceso oficial
    _logger.info("account_ux pre-migrate: marcando módulos desinstalados como uninstalled")
    modulos_desinstalados = [
        'account_tax_settlement',
        'enseco_report_custom',
        'l10n_ar_account_tax_settlement',
        'l10n_ar_account_withholding',
        'l10n_ar_purchase_stock',
        'l10n_ar_stock_adhoc',
        'l10n_ar_withholding_ux',
        'stock_account_ux',
        'stock_batch_picking_ux',
        'stock_picking_show_return',
        'stock_reserve',
        'stock_voucher',
        'web_ir_actions_act_multi',
    ]
    cr.execute("""
        UPDATE ir_module_module
        SET state = 'uninstalled'
        WHERE name = ANY(%s)
        AND state IN ('to upgrade', 'installed')
    """, (modulos_desinstalados,))
    _logger.info(f"  ✓ {cr.rowcount} módulos marcados como uninstalled")