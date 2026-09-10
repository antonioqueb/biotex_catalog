from . import controllers
from . import models
from . import wizard


def post_init_hook(env):
    """Las unidades típicas de los atributos dimensionales existen en el catálogo de unidades desde la instalación."""
    env['biotex.measure.type']._ensure_units()
