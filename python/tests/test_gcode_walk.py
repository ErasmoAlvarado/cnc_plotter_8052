"""Tests del interprete unico de G-code.

El test importante de todo este refactor es
`test_lo_que_se_ejecuta_es_lo_que_se_valida`: antes habia tres interpretes
distintos (ejecucion, limites y preview) y ya habian divergido, asi que el
limite blando validaba una geometria que no era la que se dibujaba. Si alguien
vuelve a meter un cuarto camino, ese test se cae.
"""

import pytest

from cnc_plotter import CNCPlotter
from cnc_protocol import CNCProtocol
from gcode_transform import Bounds, build, flip_y_about
from gcode_walk import (ArcEvent, DwellEvent, MoveEvent, PenEvent, bounds_of,
                        command_line_count, walk)


def geometria(eventos):
    """Todos los puntos que toca el recorrido, en orden."""
    puntos = []
    for ev in eventos:
        if isinstance(ev, MoveEvent):
            puntos.append((ev.x, ev.y))
        elif isinstance(ev, ArcEvent):
            puntos.extend(ev.points)
    return puntos


def caja(puntos):
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    return Bounds(min(xs), max(xs), min(ys), max(ys))


# ─── lo esencial del parser, que no debe haber cambiado ──────────────

def test_g90_absoluto_y_g91_relativo():
    abs_ = geometria(walk(['G90', 'G0 X10 Y10', 'G0 X10 Y10']))
    rel = geometria(walk(['G91', 'G0 X10 Y10', 'G0 X10 Y10']))
    assert abs_ == [(10, 10), (10, 10)]
    assert rel == [(10, 10), (20, 20)]


def test_umbral_de_pluma_configurable():
    """[SW-11] Un fichero con Z0 = dibujar y Z5 = levantar tiene que
    funcionar; con el 'z < 0' de la v1 salia en blanco."""
    lineas = ['G90', 'G1 X10 Z0', 'G1 X20 Z5']
    tipos = [ev.draw for ev in walk(lineas, z_pen_down_threshold=0.0)
             if isinstance(ev, MoveEvent)]
    assert tipos == [True, False]


def test_m3_baja_la_pluma_antes_del_movimiento_de_su_linea():
    """[SW-42] El estado de pluma de la linea manda sobre su propio trazo."""
    eventos = list(walk(['G90', 'M3 G1 X10']))
    assert isinstance(eventos[0], PenEvent) and eventos[0].down
    assert isinstance(eventos[1], MoveEvent) and eventos[1].draw


def test_g0_no_dibuja_nunca_y_deja_la_pluma_arriba():
    """[SW-40] Un G0 con Z en la misma linea mueve primero y aplica la Z
    despues; el trazo del rapido nunca dibuja."""
    eventos = list(walk(['G90', 'M3', 'G0 X10 Y10 Z-1']))
    movs = [e for e in eventos if isinstance(e, MoveEvent)]
    assert movs[0].draw is False
    assert eventos[-1] == PenEvent(2, True)     # la Z se aplica al final


def test_g0_con_solo_z_no_genera_movimiento():
    """Un 'G0 Z-1' suelto es bajar la pluma, no un viaje."""
    eventos = list(walk(['G90', 'G0 Z-1']))
    assert not [e for e in eventos if isinstance(e, MoveEvent)]
    assert eventos == [PenEvent(1, True)]


def test_arco_respeta_el_estado_de_pluma():
    """[SW-41] Antes cualquier G2 dibujaba aunque la pluma estuviera arriba."""
    arriba = [e for e in walk(['G90', 'G0 X10', 'G2 X0 Y0 I-5 J0'])
              if isinstance(e, ArcEvent)]
    abajo = [e for e in walk(['G90', 'G0 X10', 'M3', 'G2 X0 Y0 I-5 J0'])
             if isinstance(e, ArcEvent)]
    assert arriba[0].draw is False
    assert abajo[0].draw is True


def test_arco_termina_exactamente_en_el_destino():
    ev = [e for e in walk(['G90', 'G0 X10 Y0', 'G2 X0 Y10 I-10 J0'])
          if isinstance(e, ArcEvent)][0]
    assert ev.points[-1] == pytest.approx((0.0, 10.0))


def test_arco_con_ij_incoherente_cae_a_recta():
    """[SW-47] I/J que no cuadran con el destino dibujaban una espiral."""
    ev = [e for e in walk(['G90', 'G0 X0 Y0', 'G2 X50 Y0 I1 J0'])
          if isinstance(e, ArcEvent)][0]
    assert ev.points == ((50.0, 0.0),)


def test_g28_y_m30_viajan_al_origen():
    """Divergencia corregida: los interpretes de limites y de preview se
    saltaban este viaje, pero el carro lo hace y puede chocar."""
    assert geometria(walk(['G90', 'G0 X20 Y20', 'G28'])) == [(20, 20), (0, 0)]
    assert geometria(walk(['G90', 'G0 X20 Y20', 'M30'])) == [(20, 20), (0, 0)]


def test_dwell_se_acota_a_cinco_segundos():
    ev = [e for e in walk(['G4 P900']) if isinstance(e, DwellEvent)][0]
    assert ev.seconds == 5.0


def test_las_lineas_vacias_y_los_comentarios_no_cuentan():
    lineas = ['', '; solo un comentario', '(otro)', 'G90', 'G0 X1']
    assert command_line_count(lineas) == 2


def test_cada_evento_lleva_su_indice_de_linea():
    """El frontend empareja el 'line' del preview con el del WebSocket para
    pintar en vivo lo ya dibujado: si se desalinean, se pinta mal."""
    lineas = ['G90', '', '; nada', 'G0 X1', 'G1 X2']
    assert [e.line for e in walk(lineas) if isinstance(e, MoveEvent)] == [3, 4]


# ─── la garantia central del refactor ────────────────────────────────

def _plotter_simulado(**kwargs):
    proto = CNCProtocol(simulate=True)
    proto.connect()
    opciones = dict(steps_per_mm_x=42.67, steps_per_mm_y=42.67,
                    max_x_mm=1000.0, max_y_mm=1000.0,
                    enforce_soft_limits=False)
    opciones.update(kwargs)
    return CNCPlotter(proto, **opciones)


GCODE = [
    'G90',
    'G0 X5 Y5',
    'M3',
    'G1 X40 Y5',
    'G1 X40 Y30',
    'G2 X20 Y10 I-20 J0',
    'G1 X5 Y5',
    'M5',
    'G0 X50 Y50',
    'M30',
]


def test_lo_que_se_ejecuta_es_lo_que_se_valida():
    """La caja que comprueba el limite blando es la geometria REAL.

    Se ejecuta el G-code contra un plotter simulado registrando cada
    coordenada por la que pasa de verdad, y se compara con lo que dice
    bounds_of() —que es lo que usa el pre-vuelo de /api/run—."""
    pl = _plotter_simulado()
    visitados = []
    line_to, rapid_to = pl.line_to, pl.rapid_to
    pl.line_to = lambda x, y: (visitados.append((x, y)), line_to(x, y))[1]
    pl.rapid_to = lambda x, y: (visitados.append((x, y)), rapid_to(x, y))[1]

    pl.begin_job()
    for ev in pl.events(GCODE):
        pl.exec_event(ev)

    ejecutado = caja(visitados)
    validado = bounds_of(GCODE, pl.z_pen_down_threshold, pl.chord_tol)

    assert ejecutado.min_x == pytest.approx(validado.min_x)
    assert ejecutado.max_x == pytest.approx(validado.max_x)
    assert ejecutado.min_y == pytest.approx(validado.min_y)
    assert ejecutado.max_y == pytest.approx(validado.max_y)


def test_el_preview_recorre_la_misma_geometria_que_la_ejecucion():
    """El preview subsamplea los arcos para no mandar megabytes, pero la
    geometria de la que sale tiene que ser la misma."""
    pl = _plotter_simulado()
    puntos = geometria(walk(GCODE, chord_tol=pl.chord_tol))
    assert caja(puntos) == bounds_of(GCODE, chord_tol=pl.chord_tol)


def test_los_limites_ven_los_rapidos_no_solo_los_trazos():
    """El carro viaja en los rapidos igual que dibujando, asi que un rapido
    fuera del area choca exactamente igual."""
    b = bounds_of(['G90', 'M3', 'G1 X10 Y10', 'M5', 'G0 X500 Y0'])
    assert b.max_x == 500.0


# ─── transformaciones sobre el recorrido ─────────────────────────────

def test_el_espejo_invierte_la_curvatura_del_arco():
    """El fallo clasico de voltear Y es olvidar que G2 pasa a ser G3. Aqui
    no puede pasar porque el arco se descompone ANTES de transformarse, y
    este test lo comprueba midiendo de que lado queda la flecha del arco."""
    lineas = ['G90', 'G0 X10 Y10', 'M3', 'G2 X30 Y30 I10 J10']
    b = bounds_of(lineas)

    def flecha(transform):
        ev = [e for e in walk(lineas, transform=transform)
              if isinstance(e, ArcEvent)][0]
        (x0, y0), (x1, y1) = ev.points[0], ev.points[-1]
        mx, my = ev.points[len(ev.points) // 2]
        return (x1 - x0) * (my - y0) - (y1 - y0) * (mx - x0)

    from gcode_transform import IDENTITY
    assert flecha(IDENTITY) * flecha(flip_y_about(b)) < 0


def test_el_espejo_no_mueve_el_dibujo_de_sitio():
    b = bounds_of(GCODE)
    assert bounds_of(GCODE, transform=flip_y_about(b)) == b


def test_ajustar_al_area_deja_el_trabajo_dentro():
    grande = ['G90', 'G0 X0 Y0', 'M3', 'G1 X300 Y0', 'G1 X300 Y220', 'G1 X0 Y0']
    b = bounds_of(grande)
    t = build(b, 80.0, 80.0, fit=True)
    ajustado = bounds_of(grande, transform=t)
    assert ajustado.min_x >= -0.001 and ajustado.max_x <= 80.001
    assert ajustado.min_y >= -0.001 and ajustado.max_y <= 80.001


def test_la_transformacion_no_altera_los_indices_de_linea():
    sin = [e.line for e in walk(GCODE) if isinstance(e, (MoveEvent, ArcEvent))]
    con = [e.line for e in walk(GCODE, transform=build(bounds_of(GCODE), 80, 80,
                                                       flip_y=True, fit=True))
           if isinstance(e, (MoveEvent, ArcEvent))]
    assert sin == con


def test_los_relativos_se_resuelven_antes_de_transformar():
    """El estado del interprete va SIN transformar: si se transformase la
    posicion acumulada, cada G91 arrastraria la escala otra vez."""
    lineas = ['G91', 'G0 X10 Y0', 'G0 X10 Y0', 'G0 X10 Y0']
    t = build(Bounds(0, 30, 0, 0), 80, 80, fit=True)
    xs = [p[0] for p in geometria(walk(lineas, transform=t))]
    # tres pasos iguales siguen siendo tres pasos iguales
    assert xs[1] - xs[0] == pytest.approx(xs[2] - xs[1])
