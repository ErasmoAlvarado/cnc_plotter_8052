"""
Limites de la area util. la maquina no tiene finales de carrera.
"""

from dataclasses import dataclass

TOLERANCE_MM = 0.5


@dataclass(frozen=True)
class Violation:
    """que se salio, cuanto, y de que limite.
    estructurado para que el frontend no tenga que parsear un string"""
    axis: str          
    value: float       
    limit: float        

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
    """movimiento pedido fuera del area util"""

    def __init__(self, violation: Violation):
        super().__init__(violation.message())
        self.violation = violation


def check_point(x_mm, y_mm, max_x, max_y, tolerance=TOLERANCE_MM):
    """primera Violation que encuentra, o None si el punto entra"""
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
    """como check_point pero para una caja completa, solo hace falta mirar
    las esquinas extremas en un rectangulo alineado a los ejes"""
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
    """cuanto queda hasta el tope en ese sentido, lo usa /api/jog para
    avisar "quedan 3.2mm" en vez de tirar un 400 sin mas info"""
    if direction > 0:
        return max(0.0, max_mm + tolerance - position_mm)
    return max(0.0, position_mm + tolerance)
