"""Deja los modulos de python/ importables sin instalar el proyecto.

No hay paquete ni pyproject: los modulos se importan por nombre suelto
(`import cnc_plotter`) porque asi es como los ejecuta cnc_api.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
