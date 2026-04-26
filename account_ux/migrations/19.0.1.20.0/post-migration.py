"""
Post-migrate de account_ux 19.0.1.20.0.

Reactiva masivamente vistas AR/Adhoc que el motor upgrade.odoo.com
desactiva preventivamente durante el pre-migrate.

Basado en script manual reactivar_vistas_post_upgrade.py que validó
23 vistas como funcionales en v19.

Patrón de validación reversible:
  1. Activar la vista.
  2. Ejecutar _get_combined_arch() — fuerza validación.
  3. Si OK, queda reactivada.
  4. Si falla, restaurar active=FALSE y loggear como deuda técnica.
"""
import logging

_logger = logging.getLogger(__name__)

# 23 vistas validadas por script manual el 26-04-2026
# Source: reactivar_vistas_post_upgrade.py output
VISTAS_A_REACTIVAR = [
    # CRÍTICAS para PDF de ventas
    ('l10n_ar_sale', 'report_saleorder_document'),  # Header AR
    ('sale_ux', 'report_saleorder'),                # UX del reporte
    
    # CRÍTICAS para inventario/stock (picking)
    ('stock_ux', 'view_picking_form'),
    ('stock_ux', 'view_move_line_tree'),
    
    # Las siguientes EXCLUIDAS temporalmente
    # ('account_ux', 'view_account_invoice_filter'),
    # ('account_ux', 'view_account_payment_tree_personalization'),
    # ('account_ux', 'view_move_form'),
    # ('l10n_ar_purchase', 'report_purchaseorder_document'),
    # ('l10n_ar_purchase', 'report_purchasequotation_document'),
    # ('l10n_ar_sale', 'view_order_form'),
    # ('l10n_ar_ux', 'view_account_payment_form'),
    # ('l10n_ar_ux', 'view_partner_property_form'),
    # ('purchase_stock_ux', 'purchase_order_line_search'),
    # ('purchase_stock_ux', 'purchase_order_line_tree'),
    # ('sale_stock_ux', 'sale_order_line_usability_tree'),
    # ('sale_stock_ux', 'view_move_form'),
    # ('sale_stock_ux', 'view_order_form'),
    # ('sale_ux', 'res_config_settings_view_form_inherit'),
    # ('sale_ux', 'sale_order_line_usability_tree'),
    # ('sale_ux', 'view_order_form'),
    # ('sale_ux', 'view_sale_advance_payment_inv'),
    # ('stock_ux', 'view_stock_return_picking_form'),
    # ('stock_ux', 'view_warehouse_orderpoint_tree_editable'),
]

# EXPLÍCITAMENTE EXCLUIDA:
# l10n_ar_edi_ux.view_partner_form (id 3996) - falla validación en v19
# Requiere patch del módulo upstream, no bloqueante para go-live

# Vistas a desactivar (other_currency)
VISTAS_A_DESACTIVAR = [3974, 4594, 4263]  # l10n_ar_ux, hr_expense, l10n_ar_withholding_ux

def migrate(cr, version):
    """Desactiva vistas obsoletas y reactiva vistas AR/Adhoc validadas."""
    
    # PASO 1: Desactivar vistas con other_currency
    _logger.info("account_ux post-migrate 19.0.1.19.0: desactivando vistas con other_currency")
    cr.execute("""
        UPDATE ir_ui_view 
        SET active = FALSE 
        WHERE id = ANY(%s) AND active = TRUE
    """, (VISTAS_A_DESACTIVAR,))
    _logger.info("  ✓ %d vistas con other_currency desactivadas", cr.rowcount)

    # PASO 2: Reactivar vistas críticas
    _logger.info("account_ux post-migrate 19.0.1.19.0: reactivando vistas críticas")

    cr.execute("""
        SELECT v.id, imd.module, imd.name AS xml_name, v.active
        FROM ir_ui_view v
        JOIN ir_model_data imd
            ON imd.res_id = v.id
            AND imd.model = 'ir.ui.view'
        WHERE (imd.module, imd.name) IN %s
        ORDER BY imd.module, imd.name
    """, (tuple(VISTAS_A_REACTIVAR),))
    rows = cr.fetchall()

    if not rows:
        _logger.warning("  ⚠ Ninguna de las vistas configuradas existe en DB.")
        return

    inactivas = [r for r in rows if not r[3]]
    activas = [r for r in rows if r[3]]

    _logger.info("  Vistas configuradas: %d", len(VISTAS_A_REACTIVAR))
    _logger.info("  Vistas encontradas en DB: %d", len(rows))
    _logger.info("    - Ya activas (no-op): %d", len(activas))
    _logger.info("    - Desactivadas (a procesar): %d", len(inactivas))

    if not inactivas:
        _logger.info("  ✓ Todas las vistas ya están activas.")
        return

    for view_id, module, xml_name, _active in inactivas:
        _logger.info("    - %s.%s (id=%d)", module, xml_name, view_id)

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    reactivadas = 0
    fallidas = []

    for view_id, module, xml_name, _active in inactivas:
        xmlid = "%s.%s" % (module, xml_name)
        view = env['ir.ui.view'].browse(view_id)

        if not view.exists():
            _logger.warning("    ⚠ %s: no existe en DB, skip", xmlid)
            continue

        try:
            view.write({'active': True})
            try:
                view._get_combined_arch()
            except Exception as e:
                view.write({'active': False})
                error_msg = str(e).split('\n')[0][:300]
                fallidas.append((xmlid, view_id, error_msg))
                _logger.warning(
                    "    ⚠ %s (id=%d): validación falló, queda desactivada. Error: %s",
                    xmlid, view_id, error_msg
                )
                continue

            reactivadas += 1
            _logger.info("    ✓ %s (id=%d): reactivada", xmlid, view_id)

        except Exception as e:
            error_msg = str(e).split('\n')[0][:300]
            fallidas.append((xmlid, view_id, "Error en write: %s" % error_msg))
            _logger.warning(
                "    ✗ %s (id=%d): error en activación: %s",
                xmlid, view_id, error_msg
            )
            try:
                cr.execute("UPDATE ir_ui_view SET active = FALSE WHERE id = %s", (view_id,))
            except Exception:
                pass

    _logger.info("")
    _logger.info("  Resumen:")
    _logger.info("    ✓ Reactivadas: %d", reactivadas)
    _logger.info("    ✗ Fallidas (deuda técnica): %d", len(fallidas))

    if fallidas:
        _logger.warning("  Vistas que requieren atención manual:")
        for xmlid, view_id, error_msg in fallidas:
            _logger.warning("    - %s (id=%d): %s", xmlid, view_id, error_msg)