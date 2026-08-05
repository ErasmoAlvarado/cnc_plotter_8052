"""
convierte el gcode en una lista de puntos es ma facil de manejar en python , tambine maneja los arcos

"""

import math
import re


_GCODE_TOKEN = re.compile(r'([A-Z])\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)')


def parse_gcode_line(line):
    """parsea una linea, devuelve dict {letra: valor} o None si no hay nada"""
    line = re.sub(r'\(.*?\)', '', line)   
    line = re.sub(r';.*$', '', line)        
    line = re.sub(r'^\s*%.*$', '', line)    
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


def arc_to_segments(x0, y0, x1, y1, i, j, clockwise, chord_tol=0.005):
    """parte un arco G2 o G3 en puntos, x0 y0 inicio, x1 y1 fin.
    i j es el offset al centro en mm, chord_tol es el error de cuerda"""
    cx = x0 + i
    cy = y0 + j
    r = math.hypot(i, j)

    if r < 1e-6:
        return [(x1, y1)]


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

    if chord_tol >= r:
        n = 8
    else:
        theta_max = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - chord_tol / r)))
        n = max(8, int(math.ceil(sweep / theta_max)))
    n = min(n, 2000)                      

    points = []
    for k in range(1, n + 1):
        t = k / n
        angle = a_start - t * sweep if clockwise else a_start + t * sweep
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    points[-1] = (x1, y1)                
    return points
