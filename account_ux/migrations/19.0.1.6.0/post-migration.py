"""
Post-migrate de account_ux 19.0.1.6.0.

Reactiva vistas AR/Adhoc específicas que el motor de upgrade.odoo.com
desactiva preventivamente durante el pre-migrate ("caused validation issues.
Disabling it for the migration..."). Una vez completado el upgrade, los
modelos v19 están cargados y las vistas pueden validar correctamente.

Este post-migrate corre en account_ux (no en l10n_ar_sale) por convención
del proyecto Enseco: account_ux es el hogar de fixes cruzados de la
migración 17→19. Decisión 12 del traspaso.

Vistas que este post-migrate reactiva:
  - l10n_ar_sale.report_saleorder_document (id 4294 en stage):
    Aporta el header AR (CUIT, IIBB, condición IVA, letra X,
    leyenda "Doc no válido como factura") al reporte de cotización.
    Sin ella activa, el reporte cae al template del core sin formato AR.

Patrón de validación reversible:
  1. Activar la vista.
  2. Ejecutar _get_combined_arch() — esto fuerza al motor de QWeb a
     resolver herencias y validar xpaths contra los modelos cargados.
  3. Si OK, queda reactivada.
  4. Si falla, restaurar active=FALSE y loggear como deuda técnica.

Patrón tomado del script manual reactivar_vistas_post_upgrade.py
y del PR1 de Javier (enseco_report_custom 19.0.1.1.0).

Idempotente: si la vista ya está activa, no-op.
"""
import logging

_logger = logging.getLogger(__name__)


# Vistas a reactivar: lista de (module, name) en ir_model_data.
# Si en validación funcional aparecen más vistas bloqueantes, agregar acá
# y bumpear a 19.0.1.7.0 (no modificar 19.0.1.6.0 una vez validado).
VISTAS_A_REACTIVAR = [
    ('l10n_ar_sale', 'report_saleorder_document'),
]


def migrate(cr, version):
    """Reactiva vistas AR/Adhoc bloqueantes para reportes."""
    _logger.info(
        "account_ux post-migrate 19.0.1.6.0: "
        "reactivación quirúrgica de vistas AR/Adhoc"
    )

    if not VISTAS_A_REACTIVAR:
        _logger.info("  No hay vistas configuradas para reactivar. Nada que hacer.")
        return

    # Buscar las vistas en DB filtrando por (module, name) — nunca por id
    # hardcodeado, porque los IDs cambian entre builds.
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
        _logger.warning(
            "  ⚠ Ninguna de las vistas configuradas existe en DB. "
            "Verificar nombres en VISTAS_A_REACTIVAR."
        )
        return

    # Reportar estado inicial
    inactivas = [r for r in rows if not r[3]]
    activas = [r for r in rows if r[3]]

    _logger.info("  Vistas configuradas: %d", len(VISTAS_A_REACTIVAR))
    _logger.info("  Vistas encontradas en DB: %d", len(rows))
    _logger.info("    - Ya activas (no-op): %d", len(activas))
    _logger.info("    - Desactivadas (a procesar): %d", len(inactivas))

    if not inactivas:
        _logger.info("  ✓ Todas las vistas ya están activas. Nada que hacer.")
        return

    for view_id, module, xml_name, _active in inactivas:
        _logger.info("    - %s.%s (id=%d)", module, xml_name, view_id)

    # Construir env para usar _get_combined_arch().
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

        # Validación reversible.
        try:
            view.write({'active': True})
            try:
                view._get_combined_arch()
            except Exception as e:
                # Vista no valida en v19: restaurar y registrar deuda técnica.
                view.write({'active': False})
                error_msg = str(e).split('\n')[0][:300]
                fallidas.append((xmlid, view_id, error_msg))
                _logger.warning(
                    "    ⚠ %s (id=%d): validación falló, queda desactivada. Error: %s",
                    xmlid, view_id, error_msg
                )
                continue

            # Validación OK — dejar reactivada.
            reactivadas += 1
            _logger.info("    ✓ %s (id=%d): reactivada", xmlid, view_id)

        except Exception as e:
            error_msg = str(e).split('\n')[0][:300]
            fallidas.append((xmlid, view_id, "Error en write: %s" % error_msg))
            _logger.warning(
                "    ✗ %s (id=%d): error en activación: %s",
                xmlid, view_id, error_msg
            )
            # Intentar restaurar por las dudas (con SQL directo, sin ORM).
            try:
                cr.execute(
                    "UPDATE ir_ui_view SET active = FALSE WHERE id = %s",
                    (view_id,)
                )
            except Exception:
                pass

    _logger.info("")
    _logger.info("  Resumen:")
    _logger.info("    ✓ Reactivadas: %d", reactivadas)
    _logger.info("    ✗ Fallidas (deuda técnica): %d", len(fallidas))

    if fallidas:
        _logger.warning(
            "  Las siguientes vistas no pudieron reactivarse "
            "y requieren atención manual:"
        )
        for xmlid, view_id, error_msg in fallidas:
            _logger.warning("    - %s (id=%d): %s", xmlid, view_id, error_msg)
