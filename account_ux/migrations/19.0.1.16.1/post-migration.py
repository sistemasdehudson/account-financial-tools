# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migrate de account_ux 19.0.1.16.1

    Consolida fixes de data layer que el upgrade oficial no realiza
    y que históricamente vivían en el post-migrate de stock_ux
    (que no corre porque el módulo es 'not installable' en v19).

    Tareas:
      1. Restaurar grupo uom.group_uom a usuarios internos
      2. Repoblar product_template_uom_uom_rel desde histórico
      3. Desactivar menús huérfanos de módulos desinstalados
      4. Desactivar templates Studio con campos obsoletos
    """
    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.16.1: fixes de data layer")
    _logger.info("=" * 70)

    _restore_uom_group_to_internal_users(cr)
    _backfill_product_uom_relations(cr)
    _deactivate_orphan_menus(cr)
    _deactivate_obsolete_studio_templates(cr)

    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.16.1: completado")
    _logger.info("=" * 70)


def _restore_uom_group_to_internal_users(cr):
    """
    Restaura el grupo uom.group_uom (Manage Multiple UoMs) a usuarios internos.

    Contexto: en v17 ese grupo era asignado implícitamente por módulos como
    stock_voucher, stock_ux, account_ux. Al desinstalar varios de esos módulos
    durante el upgrade, los usuarios pierden la asignación.

    Sin este grupo, los usuarios no pueden cambiar la UoM en sale.order.line
    aunque el campo product_uom_id esté correctamente poblado.

    Idempotente: el NOT EXISTS evita re-asignar a usuarios que ya tienen el grupo.
    """
    _logger.info("Tarea 1/4: Restaurando uom.group_uom a usuarios internos")

    cr.execute("""
        INSERT INTO res_groups_users_rel (gid, uid)
        SELECT
            (SELECT g.id FROM res_groups g
             JOIN ir_model_data d ON d.res_id = g.id AND d.model = 'res.groups'
             WHERE d.module = 'uom' AND d.name = 'group_uom'),
            u.id
        FROM res_users u
        WHERE u.active = TRUE
          AND u.share = FALSE
          AND u.id != 1
          AND NOT EXISTS (
            SELECT 1 FROM res_groups_users_rel rel
            WHERE rel.uid = u.id
              AND rel.gid = (
                SELECT g.id FROM res_groups g
                JOIN ir_model_data d ON d.res_id = g.id AND d.model = 'res.groups'
                WHERE d.module = 'uom' AND d.name = 'group_uom'
              )
          )
    """)
    _logger.info("  ✓ %d usuarios recibieron el grupo uom.group_uom", cr.rowcount)


def _backfill_product_uom_relations(cr):
    """
    Repuebla product_template_uom_uom_rel desde el histórico de transacciones.

    Contexto: Odoo 19 cambió el modelo de UoMs. En v17 el dominio del campo UoM
    en líneas se filtraba por uom.category; en v19 se filtra por una m2m explícita
    product_template <-> uom_uom. El upgrade oficial crea la tabla pero no la pobla.

    El backfill toma como fuentes:
      - UoM principal del producto (siempre)
      - UoMs usadas en sale_order_line (histórico de venta)
      - UoMs usadas en stock_move (histórico de movimientos)

    No incluye purchase_order_line ni account_move_line por decisión validada
    con el cliente: lo que se valida funcionalmente es solo el flujo de venta.

    Idempotente: ON CONFLICT DO NOTHING.

    Nota técnica: en v19 sale_order_line.product_uom_id existe como _id, pero
    stock_move.product_uom mantiene el nombre v17 sin _id. El rename fue
    inconsistente entre modelos.
    """
    _logger.info("Tarea 2/4: Repoblando product_template_uom_uom_rel")

    cr.execute("""
        INSERT INTO product_template_uom_uom_rel (product_template_id, uom_uom_id)
        SELECT DISTINCT product_tmpl_id, uom_id
        FROM (
            -- 1. UoM default del producto
            SELECT pt.id AS product_tmpl_id, pt.uom_id AS uom_id
            FROM product_template pt
            WHERE pt.uom_id IS NOT NULL

            UNION

            -- 2. UoMs usadas en líneas de venta históricas
            SELECT pp.product_tmpl_id, sol.product_uom_id AS uom_id
            FROM sale_order_line sol
            JOIN product_product pp ON pp.id = sol.product_id
            WHERE sol.product_uom_id IS NOT NULL

            UNION

            -- 3. UoMs usadas en movimientos de stock (campo legacy product_uom)
            SELECT pp.product_tmpl_id, sm.product_uom AS uom_id
            FROM stock_move sm
            JOIN product_product pp ON pp.id = sm.product_id
            WHERE sm.product_uom IS NOT NULL
        ) combos
        WHERE EXISTS (
            SELECT 1 FROM uom_uom u
            WHERE u.id = combos.uom_id AND u.active = TRUE
        )
        ON CONFLICT DO NOTHING
    """)
    _logger.info(
        "  ✓ %d filas insertadas en product_template_uom_uom_rel",
        cr.rowcount
    )

    # Sanity check: log estadísticas finales
    cr.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT product_template_id) AS productos,
            COUNT(DISTINCT uom_uom_id) AS uoms
        FROM product_template_uom_uom_rel
    """)
    total, productos, uoms = cr.fetchone()
    _logger.info(
        "  ✓ Estado final: %d filas totales, %d productos, %d UoMs distintas",
        total, productos, uoms
    )


def _deactivate_orphan_menus(cr):
    """
    Desactiva menús de módulos que se desinstalaron en el upgrade.

    Contexto: el upgrade oficial desactiva vistas de módulos not installable,
    pero no toca los menús asociados. Esos menús quedan visibles en la UI
    pero apuntan a acciones rotas o a modelos inexistentes, generando errores
    al hacer click.

    Lista de módulos cubierta: la misma del post-migrate original de stock_ux,
    más los identificados en el ciclo del 2026-04-24 (l10n_ar_account_*).

    Idempotente: el AND m.active = TRUE filtra los ya desactivados.
    """
    _logger.info("Tarea 3/4: Desactivando menús huérfanos")

    modules_orphan = (
        'stock_voucher', 'stock_reserve', 'stock_batch_picking_ux',
        'l10n_ar_stock_adhoc', 'l10n_ar_account_withholding',
        'account_tax_settlement', 'l10n_ar_account_tax_settlement',
        'stock_account_ux', 'enseco_report_custom',
        'stock_picking_show_return',
    )

    cr.execute("""
        UPDATE ir_ui_menu m
        SET active = FALSE
        FROM ir_model_data d
        WHERE m.id = d.res_id
          AND d.model = 'ir.ui.menu'
          AND d.module = ANY(%s)
          AND m.active = TRUE
    """, (list(modules_orphan),))
    _logger.info("  ✓ %d menús huérfanos desactivados", cr.rowcount)


def _deactivate_obsolete_studio_templates(cr):
    """
    Desactiva templates de Odoo Studio que tienen campos eliminados en v19.

    Contexto: en v17 el cliente creó templates Studio que referencian campos
    como product_uom (renombrado en v19 a product_uom_id) y product_packaging_id
    (eliminado). Si un usuario intenta imprimir esos templates en v19, falla.

    Identificación por contenido del arch_db, no por ID hardcodeado, para que
    el script siga funcionando aunque los IDs cambien entre ciclos.

    Pendiente con cliente (Facundo): confirmar si reemplaza estos templates
    Studio por los reportes nuevos de enseco_report_custom v19, o si hay que
    reconstruirlos. Hasta esa decisión, los dejamos desactivados.

    Idempotente: AND v.active = TRUE filtra los ya desactivados.
    """
    _logger.info("Tarea 4/4: Desactivando templates Studio obsoletos")

    cr.execute("""
        UPDATE ir_ui_view v
        SET active = FALSE
        FROM ir_model_data d
        WHERE v.id = d.res_id
          AND d.model = 'ir.ui.view'
          AND d.module = 'studio_customization'
          AND v.active = TRUE
          AND (
              -- product_uom referenciado sin product_uom_id (campo v17)
              (v.arch_db::text LIKE '%product_uom%'
               AND NOT v.arch_db::text LIKE '%product_uom_id%')
              -- product_packaging_id (eliminado en v19)
              OR v.arch_db::text LIKE '%product_packaging_id%'
          )
    """)
    _logger.info(
        "  ✓ %d templates Studio con campos obsoletos desactivados",
        cr.rowcount
    )