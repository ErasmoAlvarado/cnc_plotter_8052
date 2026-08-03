"""
gcode_walk.py — El UNICO interprete de G-code del proyecto.

Antes habia tres, y ya habian divergido:

  1. CNCPlotter._exec_gcode      — el que mueve la maquina de verdad
  2. gcode_bounds()              — el que valida el area (ignoraba G28)
  3. el bucle de /api/upload-gcode — el del preview (ignoraba G28, G4, y el
                                     estado de pluma que deja un G0)

O sea que "lo que se ve en pantalla", "lo que se comprueba contra los limites"
y "lo que sale por el puerto serie" eran tres lecturas distintas del mismo
fichero. Con eso, un limite blando no vale de nada: valida una geometria que
no es la que se va a dibujar.

walk() emite una secuencia de eventos con la geometria YA resuelta (absoluta,
en mm, con la transformacion aplicada). Los tres consumidores se limitan a
reaccionar a los mismos eventos, asi que por construccion ven lo mismo.

────────────────────────────────────────────────────────────────────────
LO QUE SE CONSERVA DEL COMPORTAMIENTO ORIGINAL
────────────────────────────────────────────────────────────────────────
  [SW-42] M3/M4 (pluma abajo) y M5 (arriba) se aplican ANTES del movimiento
          de su propia linea; M2/M30 son fin de programa y van despues.
  [SW-40] En G0 el movimiento va primero y la Z de esa linea despues, y solo
          se sube la pluma si el rapido mueve algo.
  [SW-41] G2/G3 respetan el estado de pluma en vez de forzar el trazo.
  [SW-11] La Z del G-code se traduce con umbral configurable, no con 'z < 0'.
  [SW-19] El arco se emite como UN evento con todos sus puntos, para que
          quien ejecuta fije la velocidad una sola vez y no por segmento.

Diferencia deliberada respecto a los interpretes viejos: G28 y M2/M30 ahora
emiten su viaje al origen como un rapido normal, asi que cuentan para la caja
delimitadora. El carro viaja de verdad hasta alli y podia chocar sin que
ninguna comprobacion se enterase.
"""

from dataclasses import dataclass
from typing import Tuple

from gcode_parse import arc_to_segments, parse_gcode_line
from gcode_transform import IDENTITY, Bounds, GcodeTransform


# ─── EVENTOS ─────────────────────────────────────────────────────────
# Inmutables: el walker los produce y nadie los modifica por el camino.

@dataclass(frozen=True)
class PenEvent:
    """Cambio explicito de pluma (M3/M4/M5 o la Z de la linea)."""
    line: int
    down: bool


@dataclass(frozen=True)
class MoveEvent:
    """Movimiento recto hasta (x, y) absolutos en mm, ya transformados."""
    line: int
    x: float
    y: float
    draw: bool


@dataclass(frozen=True)
class ArcEvent:
    """Arco ya descompuesto en puntos absolutos en mm, ya transformados.

    Llega entero y no punto a punto para que el ejecutor pueda fijar la
    velocidad una sola vez [SW-19]."""
    line: int
    points: Tuple[Tuple[float, float], ...]
    draw: bool


@dataclass(frozen=True)
class DwellEvent:
    line: int
    seconds: float


# ─── RECORRIDO ───────────────────────────────────────────────────────

def walk(lines, z_pen_down_threshold=0.0, chord_tol=0.005,
         transform: GcodeTransform = IDENTITY, initial_pen_down=False):
    """Recorre el G-code y emite eventos con la geometria resuelta.

    lines: iterable de lineas de texto.
    z_pen_down_threshold: Z <= umbral significa pluma abajo [SW-11].
    chord_tol: error maximo de cuerda al descomponer arcos, en mm.
    transform: espejo/escala/traslacion a aplicar a la geometria emitida.
    initial_pen_down: estado real de la pluma al empezar. El ejecutor pasa
        proto.pen_down_flag; el preview y los limites pasan False. Es la
        unica diferencia legitima entre los tres, y por eso es un parametro
        explicito y no una suposicion escondida.

    El estado del interprete (gx, gy) se lleva SIN transformar: los
    movimientos relativos de G91 y los offsets I/J de los arcos son
    relativos a la coordenada original del fichero. La transformacion se
    aplica solo al emitir.
    """
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

        # [SW-42] El estado de pluma de una linea manda sobre el trazo de
        # esa misma linea, asi que M3/M4/M5 van ANTES del movimiento.
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

            if g_int == 0:                              # rapido
                # [SW-40] Primero el viaje, despues la Z de la linea. Y solo
                # se considera "viaje" si hay X o Y: un "G0 Z-1" suelto es
                # una bajada de pluma, no un desplazamiento.
                if 'X' in params or 'Y' in params:
                    x, y = _resolve_xy(params, abs_mode, gx, gy)
                    # rapid_to() sube la pluma antes de moverse; no hace
                    # falta emitirlo, pero el estado interno tiene que
                    # reflejarlo o la siguiente linea decidiria mal.
                    pen_down = False
                    yield MoveEvent(idx, *t.apply(x, y), draw=False)
                    gx, gy = x, y
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)

            elif g_int == 1:                            # lineal
                x, y = _resolve_xy(params, abs_mode, gx, gy)
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)
                yield MoveEvent(idx, *t.apply(x, y), draw=pen_down)
                gx, gy = x, y

            elif g_int in (2, 3):                       # arcos
                x, y = _resolve_xy(params, abs_mode, gx, gy)
                pen_down = yield from _apply_z(params, idx, pen_down,
                                               z_pen_down_threshold)
                # [SW-41] El arco respeta la pluma, no la fuerza.
                pts = arc_to_segments(gx, gy, x, y,
                                      params.get('I', 0.0),
                                      params.get('J', 0.0),
                                      g_int == 2, chord_tol)
                # Se espeja/escala DESPUES de descomponer: espejar una
                # polilinea no tiene casos especiales, mientras que espejar
                # un arco obligaria a invertir G2<->G3 y el signo de J.
                yield ArcEvent(idx, tuple(t.apply(px, py) for px, py in pts),
                               draw=pen_down)
                gx, gy = x, y

            elif g_int == 4:                            # dwell
                yield DwellEvent(idx, min(5.0, max(0.0, params.get('P', 0.0))))

            elif g_int == 28:                           # home
                pen_down = False
                yield MoveEvent(idx, *t.apply(0.0, 0.0), draw=False)
                gx = gy = 0.0

            elif g_int == 90:
                abs_mode = True
            elif g_int == 91:
                abs_mode = False
            # G20/G21: solo trabajamos en mm, se ignoran

        if m is not None and int(m) in (2, 30):         # fin de programa
            pen_down = False
            yield MoveEvent(idx, *t.apply(0.0, 0.0), draw=False)
            gx = gy = 0.0


def _resolve_xy(params, abs_mode, gx, gy):
    if abs_mode:
        return params.get('X', gx), params.get('Y', gy)
    return gx + params.get('X', 0.0), gy + params.get('Y', 0.0)


def _apply_z(params, idx, pen_down, threshold):
    """[SW-11] Z del G-code -> pluma arriba/abajo, con umbral configurable.

    Emite el evento aunque el estado no cambie: quien ejecuta ya lo filtra
    con su propia cache [SW-46], y el preview lo ignora."""
    z = params.get('Z')
    if z is None:
        return pen_down
    down = z <= threshold
    yield PenEvent(idx, down)
    return down


# ─── CAJA DELIMITADORA ───────────────────────────────────────────────

def bounds_of(lines, z_pen_down_threshold=0.0, chord_tol=0.005,
              transform: GcodeTransform = IDENTITY) -> Bounds:
    """Caja delimitadora de TODO lo que se mueve, rapidos incluidos.

    Los rapidos cuentan porque el carro viaja igual y puede chocar contra el
    tope aunque no dibuje nada.
    """
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

    if min_x == float('inf'):               # fichero sin movimiento alguno
        return Bounds(0.0, 0.0, 0.0, 0.0)
    return Bounds(min_x, max_x, min_y, max_y)


def command_line_count(lines) -> int:
    """Cuantas lineas del fichero son ordenes de verdad (no comentarios ni
    lineas vacias). Solo es un dato para la interfaz."""
    return sum(1 for raw in lines if parse_gcode_line(raw) is not None)
