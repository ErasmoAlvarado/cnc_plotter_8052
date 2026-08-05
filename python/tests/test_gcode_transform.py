"""tests de gcode_transform: espejo en Y y ajuste al area. lo que importa
aca es que la transformacion no deforme el dibujo y que "ajustar al area"
de verdad lo deje adentro de los limites"""

import math

import pytest

from gcode_transform import (IDENTITY, Bounds, GcodeTransform, build,
                             fit_to_area, flip_y_about)


# identidad

def test_identidad_no_toca_nada():
    assert IDENTITY.apply(3.5, -7.25) == (3.5, -7.25)
    assert IDENTITY.is_identity


def test_build_sin_opciones_es_la_identidad():
    b = Bounds(0, 10, 0, 10)
    assert build(b, 80, 80).is_identity


# espejo en Y

def test_espejo_conserva_la_caja():
    """espejar sobre el centro del propio dibujo no lo mueve de sitio,
    por eso no se espeja sobre max_y_mm"""
    b = Bounds(10, 40, 10, 30)
    t = flip_y_about(b)
    ys = [t.apply(0, y)[1] for y in (b.min_y, b.max_y)]
    assert min(ys) == pytest.approx(b.min_y)
    assert max(ys) == pytest.approx(b.max_y)


def test_espejo_es_su_propia_inversa():
    b = Bounds(0, 10, 4, 16)
    t = flip_y_about(b)
    for y in (4.0, 7.5, 10.0, 16.0):
        vuelta = t.apply(0, t.apply(0, y)[1])[1]
        assert vuelta == pytest.approx(y)


def test_espejo_no_toca_la_x():
    t = flip_y_about(Bounds(0, 10, 0, 10))
    assert t.apply(3.0, 1.0)[0] == pytest.approx(3.0)


def test_espejo_invierte_el_orden_vertical():
    """lo de arriba pasa a estar abajo, es el punto del ajuste"""
    t = flip_y_about(Bounds(0, 10, 0, 10))
    assert t.apply(0, 2.0)[1] > t.apply(0, 8.0)[1]


# ajuste al area

def test_ajuste_mete_el_dibujo_en_el_area():
    b = Bounds(0, 200, 0, 150)
    t = fit_to_area(b, 80, 80, margin_mm=1.0)
    esquinas = [t.apply(x, y) for x in (b.min_x, b.max_x) for y in (b.min_y, b.max_y)]
    for x, y in esquinas:
        assert -0.001 <= x <= 80.001
        assert -0.001 <= y <= 80.001


def test_ajuste_conserva_la_proporcion():
    """escala uniforme, un circulo no puede salir ovalado"""
    b = Bounds(0, 200, 0, 150)
    t = fit_to_area(b, 80, 80)
    ancho = t.apply(b.max_x, 0)[0] - t.apply(b.min_x, 0)[0]
    alto = t.apply(0, b.max_y)[1] - t.apply(0, b.min_y)[1]
    assert ancho / alto == pytest.approx(b.width / b.height)


def test_ajuste_nunca_agranda():
    """cabe? se recoloca nomas, no se infla para llenar el area"""
    t = fit_to_area(Bounds(0, 10, 0, 10), 80, 80)
    assert t.scale == pytest.approx(1.0)


def test_ajuste_recoloca_coordenadas_negativas():
    """cabe por tamano pero esta mal ubicado, solo hay que moverlo"""
    b = Bounds(-30, -10, -30, -10)
    t = fit_to_area(b, 80, 80)
    for x, y in ((b.min_x, b.min_y), (b.max_x, b.max_y)):
        nx, ny = t.apply(x, y)
        assert 0 <= nx <= 80 and 0 <= ny <= 80


def test_ajuste_de_una_linea_recta_no_divide_por_cero():
    """altura cero es valido, una linea horizontal nomas"""
    t = fit_to_area(Bounds(0, 200, 5, 5), 80, 80)
    x, y = t.apply(200, 5)
    assert math.isfinite(x) and math.isfinite(y)
    assert 0 <= x <= 80


# composicion

def test_espejo_y_ajuste_se_componen_en_una_sola_transformacion():
    b = Bounds(0, 200, 0, 150)
    t = build(b, 80, 80, flip_y=True, fit=True)
    assert t.flip_y and t.scale < 1.0
    for x in (b.min_x, b.max_x):
        for y in (b.min_y, b.max_y):
            nx, ny = t.apply(x, y)
            assert -0.001 <= nx <= 80.001 and -0.001 <= ny <= 80.001


def test_build_parte_siempre_de_la_caja_original():
    """pulsar "ajustar al area" dos veces no encoge el dibujo dos veces"""
    b = Bounds(0, 200, 0, 150)
    assert build(b, 80, 80, fit=True) == build(b, 80, 80, fit=True)


def test_transform_es_inmutable():
    t = GcodeTransform(scale=2.0)
    with pytest.raises(Exception):
        t.scale = 3.0
