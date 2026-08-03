"""
soft_limits.py — Limites blandos del area util.

La maquina NO tiene finales de carrera. Si un dibujo se sale del area, el
carro llega al tope mecanico, el motor sigue pulsando, se pierden pasos y la
calibracion se va al garete: a partir de ese momento el software cree estar en
un sitio y la maquina esta en otro. Recuperarse de eso es rehacer la
calibracion entera.

Por eso los limites son lo unico que puede parar un trabajo antes de empezar.

DOS NIVELES, a proposito:

  1. check_bounds() sobre la caja delimitadora, ANTES de mover nada. Es el que
     de verdad protege: da un mensaje accionable ("el dibujo mide 120 mm y el
     area son 80") y no deja salir ni un byte por el puerto serie.

  2. check_point() en cada movimiento, como ultima red. Si el pre-vuelo paso,
     este no deberia dispararse nunca — salvo que el usuario haya movido el
     origen a mano entre medias, que es justo el caso que el pre-vuelo no
     puede prever.

La tolerancia de 0.5 mm existe desde la v1: el redondeo mm->pasos y el ultimo
punto de un arco pueden dejar decimas por fuera sin que eso signifique nada
mecanicamente.
"""

from dataclasses import dataclass

TOLERANCE_MM = 0.5


@dataclass(frozen=True)
class Violation:
    """Que se salio, cuanto, y de que limite. Estructurado y no un string
    para que la API pueda devolverselo al frontend y este pinte el aviso sin
    tener que parsear texto."""
    axis: str           # 'x' | 'y'
    value: float        # coordenada pedida, en mm
    limit: float        # limite superado, en mm (0 o max_*)

    @property
    def excess_mm(self) -> float:
        return abs(self.value - self.limit)

    def message(self) -> str:
        lado = "por debajo de" if self.value < self.limit else "por encima de"
        return (f"El eje {self.axis.upper()} se sale {self.excess_mm:.1f} mm "
                f"{lado} {self.limit:.1f} mm")

    def as_dict(self) -> dict:
        return {"axis": self.axis, "value": round(self.value, 3),
                "limit": round(self.limit, 3),
                "excess_mm": round(self.excess_mm, 3),
                "message": self.message()}


class LimitExceeded(Exception):
    """Se pidio un movimiento fuera del area util."""

    def __init__(self, violation: Violation):
        super().__init__(violation.message())
        self.violation = violation


def check_point(x_mm, y_mm, max_x, max_y, tolerance=TOLERANCE_MM):
    """Devuelve la primera Violation encontrada, o None si el punto cabe."""
    if x_mm < -tolerance:
        return Violation('x', x_mm, 0.0)
    if x_mm > max_x + tolerance:
        return Violation('x', x_mm, max_x)
    if y_mm < -tolerance:
        return Violation('y', y_mm, 0.0)
    if y_mm > max_y + tolerance:
        return Violation('y', y_mm, max_y)
    return None


def check_bounds(bounds, max_x, max_y, tolerance=TOLERANCE_MM):
    """Igual que check_point pero sobre una caja completa (gcode_transform.Bounds).

    Se comprueban las esquinas extremas, que son las unicas que pueden violar
    un rectangulo alineado con los ejes."""
    if bounds.min_x < -tolerance:
        return Violation('x', bounds.min_x, 0.0)
    if bounds.max_x > max_x + tolerance:
        return Violation('x', bounds.max_x, max_x)
    if bounds.min_y < -tolerance:
        return Violation('y', bounds.min_y, 0.0)
    if bounds.max_y > max_y + tolerance:
        return Violation('y', bounds.max_y, max_y)
    return None


def fits(bounds, max_x, max_y, tolerance=TOLERANCE_MM) -> bool:
    return check_bounds(bounds, max_x, max_y, tolerance) is None


def remaining_mm(position_mm, direction, max_mm, tolerance=TOLERANCE_MM) -> float:
    """Cuanto queda hasta el tope en ese sentido. Lo usa /api/jog para poder
    decir "solo quedan 3.2 mm" en vez de un 400 pelado."""
    if direction > 0:
        return max(0.0, max_mm + tolerance - position_mm)
    return max(0.0, position_mm + tolerance)
