"""
el unico interprete de g-code de todo el proyecto.
antes habia tres, ejecucion, validacion de limites y preview, y se desincronizaban.
el limite blando no validaba lo que en realidad se iba a dibujar.
ahora walk emite eventos con la geometria ya resuelta y los tres consumidores
CNCPlotter, bounds_of y el preview de la api solo reaccionan a esos eventos.

M3, M4 y M5 se aplican antes del movimiento de su propia linea.
G28, M2 y M30 mandan su viaje de vuelta al origen como un rapido mas
asi que cuenta para la caja delimitadora, el carro viaja ahi de verdad.
"""

from dataclasses import dataclass
from typing import Tuple

from gcode_parse import arc_to_segments, parse_gcode_line
from gcode_transform import IDENTITY, Bounds, GcodeTransform


# eventos inmutables, el walker los emite y nadie los toca despues

@dataclass(frozen=True)
class PenEvent:
    line: int
    down: bool


@dataclass(frozen=True)
class MoveEvent:
    line: int
    x: float
    y: float
    draw: bool


@dataclass(frozen=True)
class ArcEvent:
    """arco ya descompuesto en puntos, mm absolutos y transformados.
    viene entero, no punto a punto, para fijar la velocidad una sola vez"""
    line: int
    points: Tuple[Tuple[float, float], ...]
    draw: bool


@dataclass(frozen=True)
class DwellEvent:
    line: int
    seconds: float


def walk(lines, z_pen_down_threshold=0.0, chord_tol=0.005,
         transform: GcodeTransform = IDENTITY, initial_pen_down=False):
    """recorre el g-code linea por linea y emite los eventos de arriba."""
    abs_mode = True
    gx = gy = 0.0
    pen_down = bool(initial_pen_down)
    t = transform

    for idx, raw in enumerate(lines):
        params = parse_gcode_line(raw)
        if params is None:
            continue

        g = params.get('G')
        m = params.get('M')

        if m is not None:
            m_int = int(m)
            if m_int in (3, 4):
                pen_down = True
                yield PenEvent(idx, True)
            elif m_int == 5:
                pen_down = False
                yield PenEvent(idx, False)

        if g is not None:
            g_int = int(g)

            if g_int == 0:                              
                if 'X' in params or 'Y' in params:
                    x, y = _resolve_xy(params, abs_mode, gx, gy)
                    pen_down = False
                    yield MoveEvent(idx, *t.apply(x, y), draw=False)
                    gx, gy = x, y
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)

            elif g_int == 1:                            
                x, y = _resolve_xy(params, abs_mode, gx, gy)
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)
                yield MoveEvent(idx, *t.apply(x, y), draw=pen_down)
                gx, gy = x, y

            elif g_int in (2, 3):                       
                x, y = _resolve_xy(params, abs_mode, gx, gy)
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)
                pts = arc_to_segments(gx, gy, x, y,
                                      params.get('I', 0.0),
                                      params.get('J', 0.0),
                                      g_int == 2, chord_tol)
                yield ArcEvent(idx, tuple(t.apply(px, py) for px, py in pts),
                               draw=pen_down)
                gx, gy = x, y

            elif g_int == 4:                            
                yield DwellEvent(idx, min(5.0, max(0.0, params.get('P', 0.0))))

            elif g_int == 28:                          
                pen_down = False
                yield MoveEvent(idx, *t.apply(0.0, 0.0), draw=False)
                gx = gy = 0.0

            elif g_int == 90:
                abs_mode = True
            elif g_int == 91:
                abs_mode = False

        if m is not None and int(m) in (2, 30):         # fin de programa
            pen_down = False
            yield MoveEvent(idx, *t.apply(0.0, 0.0), draw=False)
            gx = gy = 0.0


def _resolve_xy(params, abs_mode, gx, gy):
    if abs_mode:
        return params.get('X', gx), params.get('Y', gy)
    return gx + params.get('X', 0.0), gy + params.get('Y', 0.0)


def _apply_z(params, idx, pen_down, threshold):
    """Z del g-code decide pluma arriba o abajo, con umbral configurable.
    si no hay Z, no cambia el estado de la pluma"""
    z = params.get('Z')
    if z is None:
        return pen_down
    down = z <= threshold
    yield PenEvent(idx, down)
    return down


def bounds_of(lines, z_pen_down_threshold=0.0, chord_tol=0.005,
              transform: GcodeTransform = IDENTITY) -> Bounds:
    """caja de todo lo que se mueve, rapidos incluidos.
    el carro viaja igual aunque no dibuje, y puede chocar contra el tope"""
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')

    for ev in walk(lines, z_pen_down_threshold, chord_tol, transform):
        if isinstance(ev, MoveEvent):
            puntos = ((ev.x, ev.y),)
        elif isinstance(ev, ArcEvent):
            puntos = ev.points
        else:
            continue
        for px, py in puntos:
            if px < min_x:
                min_x = px
            if px > max_x:
                max_x = px
            if py < min_y:
                min_y = py
            if py > max_y:
                max_y = py

    if min_x == float('inf'):               # archivo sin ningun movimiento
        return Bounds(0.0, 0.0, 0.0, 0.0)
    return Bounds(min_x, max_x, min_y, max_y)


def command_line_count(lines) -> int:
    """cuenta lineas que son ordenes reales, sin comentarios ni vacias.
    es solo un dato para mostrar en la interfaz"""
    return sum(1 for raw in lines if parse_gcode_line(raw) is not None)
