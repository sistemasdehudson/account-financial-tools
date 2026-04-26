"""
Post-migrate de account_ux 19.0.1.22.0.

Limpieza de campos obsoletos. NO reactiva vistas críticas.
La reactivación de vistas ahora la hace stock_ux 19.0.1.7.0.
"""
import logging

_logger = logging.getLogger(__name__)

# Lista vacía - no reactivamos nada aquí
VISTAS_A_REACTIVAR = []


def migrate(cr, version):
    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.22.0: solo limpieza")
    _logger.info("=" * 70)

    _logger.info("  Nota: la reactivación de vistas críticas la hace stock_ux")

    _logger.info("=" * 70)
    _logger.info("account_ux post-migrate 19.0.1.22.0: completado")
    _logger.info("=" * 70)