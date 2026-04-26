"""
Post-migrate de account_ux 19.0.1.21.0.

Solo limpieza de campos obsoletos. La reactivación de vistas críticas
se maneja ahora en stock_ux post-migrate 19.0.1.5.0.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.21.0: limpieza de campos obsoletos")
    _logger.info("=" * 70)

    # Nota: la reactivación de vistas críticas ahora la hace stock_ux
    _logger.info("  Nota: las vistas críticas se reactivan en stock_ux post-migrate")

    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.21.0: completado")
    _logger.info("=" * 70)