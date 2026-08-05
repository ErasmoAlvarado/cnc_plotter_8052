"""deja los modulos de python/ importables sin instalar nada. no hay
paquete ni pyproject, se importan por nombre suelto (import cnc_plotter)
pq asi los corre cnc_api.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
