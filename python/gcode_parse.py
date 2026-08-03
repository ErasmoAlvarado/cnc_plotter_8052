"""
gcode_parse.py — Lexico del G-code y descomposicion de arcos.

Estaba dentro de cnc_plotter.py. Se saco a su propio modulo porque
gcode_walk.py lo necesita y cnc_plotter.py importa gcode_walk: dejarlo donde
estaba creaba un import circular.

Es codigo movido tal cual, sin cambios de comportamiento. cnc_plotter.py
sigue re-exportando los dos nombres para no romper a quien ya los importaba
desde alli.
"""

import math
import re


# ─── PARSER G-CODE ───────────────────────────────────────────────────

# [SW-25] acepta  X10  X-10  X+10  X.5  X1.5e2
_GCODE_TOKEN = re.compile(r'([A-Z])\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)')


def parse_gcode_line(line):
    """Parsea una linea de G-code. Retorna dict {letra: valor} o None."""
    line = re.sub(r'\(.*?\)', '', line)     # comentarios entre parentesis
    line = re.sub(r';.*$', '', line)        # comentarios con ;
    line = re.sub(r'^\s*%.*$', '', line)    # delimitadores de programa
    line = line.strip().upper()
    if not line:
        return None

    params = {}
    for m in _GCODE_TOKEN.finditer(line):
        try:
            params[m.group(1)] = float(m.group(2))
        except ValueError:
            continue
    return params if params else None


# ─── ARCOS -> SEGMENTOS DE LINEA ────────────────────────────────────

def arc_to_segments(x0, y0, x1, y1, i, j, clockwise, chord_tol=0.005):
    """Descompone un arco G2/G3 en segmentos rectos.
    (x0,y0) inicio, (x1,y1) fin, (i,j) offset del inicio al centro, en mm.
    chord_tol: error maximo de cuerda en mm. Retorna lista de puntos (x,y)."""
    cx = x0 + i
    cy = y0 + j
    r = math.hypot(i, j)

    if r < 1e-6:
        return [(x1, y1)]

    # [SW-47] En un arco valido el destino esta a la misma distancia del
    # centro que el origen. Si no lo esta, el G-code trae I/J erroneos
    # (post-procesador roto, o un G2 sin I/J heredando los anteriores) y
    # el bucle de abajo dibujaria una espiral que no cierra donde toca.
    # Mejor una recta hasta el destino que un trazo fantasma.
    r_end = math.hypot(x1 - cx, y1 - cy)
    if abs(r_end - r) > max(0.05, r * 0.01):
        return [(x1, y1)]

    a_start = math.atan2(y0 - cy, x0 - cx)
    a_end = math.atan2(y1 - cy, x1 - cx)

    if clockwise:
        sweep = a_start - a_end
    else:
        sweep = a_end - a_start
    if sweep <= 1e-9:
        sweep += 2.0 * math.pi

    # segmentos adaptativos: error_cuerda = r * (1 - cos(theta/2))
    if chord_tol >= r:
        n = 8
    else:
        theta_max = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - chord_tol / r)))
        n = max(8, int(math.ceil(sweep / theta_max)))
    n = min(n, 2000)                       # techo de seguridad

    points = []
    for k in range(1, n + 1):
        t = k / n
        angle = a_start - t * sweep if clockwise else a_start + t * sweep
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    points[-1] = (x1, y1)                  # cerrar exacto en el destino
    return points
