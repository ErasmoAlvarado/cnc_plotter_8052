"""tests de los limites blandos - sin finales de carrera esto es lo unico
que evita que el carro llegue al tope y pierda pasos"""

import pytest

from cnc_plotter import CNCPlotter
from cnc_protocol import CNCProtocol
from gcode_transform import Bounds
from soft_limits import (TOLERANCE_MM, LimitExceeded, check_bounds,
                         check_point, fits, remaining_mm)


# comprobacion de punto

def test_dentro_del_area_no_es_violacion():
    assert check_point(40, 40, 80, 80) is None


@pytest.mark.parametrize("x,y,eje", [
    (-5, 40, 'x'), (85, 40, 'x'), (40, -5, 'y'), (40, 85, 'y'),
])
def test_fuera_del_area_identifica_el_eje(x, y, eje):
    v = check_point(x, y, 80, 80)
    assert v is not None and v.axis == eje


def test_la_tolerancia_deja_pasar_el_redondeo():
    """el redondeo mm->pasos puede dejar decimas de mas sin que importe"""
    assert check_point(80 + TOLERANCE_MM / 2, 0, 80, 80) is None
    assert check_point(80 + TOLERANCE_MM * 2, 0, 80, 80) is not None


def test_el_mensaje_dice_cuanto_se_pasa():
    v = check_point(95, 10, 80, 80)
    assert "15.0 mm" in v.message()
    assert v.as_dict()["excess_mm"] == 15.0


# comprobacion de caja

def test_caja_dentro_del_area():
    assert fits(Bounds(0, 80, 0, 80), 80, 80)


def test_caja_que_se_sale_por_arriba():
    v = check_bounds(Bounds(0, 40, 0, 120), 80, 80)
    assert v is not None and v.axis == 'y' and v.limit == 80


def test_caja_con_coordenadas_negativas():
    v = check_bounds(Bounds(-10, 40, 0, 40), 80, 80)
    assert v is not None and v.axis == 'x' and v.limit == 0.0


# cuanto queda hasta el tope

def test_lo_que_queda_hacia_delante_y_hacia_atras():
    assert remaining_mm(30, +1, 80) == pytest.approx(50 + TOLERANCE_MM)
    assert remaining_mm(30, -1, 80) == pytest.approx(30 + TOLERANCE_MM)


def test_lo_que_queda_nunca_es_negativo():
    assert remaining_mm(200, +1, 80) == 0.0


# integracion con el plotter

def _plotter(**kwargs):
    proto = CNCProtocol(simulate=True)
    proto.connect()
    opciones = dict(steps_per_mm_x=42.67, steps_per_mm_y=42.67,
                    max_x_mm=80.0, max_y_mm=80.0)
    opciones.update(kwargs)
    return CNCPlotter(proto, **opciones)


def test_un_movimiento_fuera_de_area_se_detiene():
    pl = _plotter()
    with pytest.raises(LimitExceeded):
        pl.line_to(200, 0)


def test_el_movimiento_bloqueado_no_movio_nada():
    """la comprobacion va antes de mandar pasos, si salta el carro no
    se movio y la posicion cacheada sigue siendo cierta"""
    pl = _plotter()
    antes = pl.proto.pos_x
    with pytest.raises(LimitExceeded):
        pl.line_to(200, 0)
    assert pl.proto.pos_x == antes


def test_desactivar_los_limites_los_desactiva_de_verdad():
    pl = _plotter(enforce_soft_limits=False)
    pl.line_to(200, 0)
    assert pl.gc_x == 200


def test_un_trabajo_que_no_cabe_no_mueve_nada():
    pl = _plotter()
    antes = (pl.proto.pos_x, pl.proto.pos_y)
    ok = pl.plot_gcode_lines(['G90', 'M3', 'G1 X300 Y0'])
    assert ok is False
    assert (pl.proto.pos_x, pl.proto.pos_y) == antes


def test_un_trabajo_que_cabe_se_ejecuta():
    pl = _plotter()
    assert pl.plot_gcode_lines(['G90', 'M3', 'G1 X40 Y40']) is True
    assert pl.gc_x == pytest.approx(40, abs=0.05)
