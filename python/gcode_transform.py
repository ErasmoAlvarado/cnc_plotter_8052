"""
tranforma el gcode ya convetido en gcode parse, las invierte , la puede centrar etc
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    """limiysviones de la geometria"""
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def as_dict(self) -> dict:
        return {"min_x": self.min_x, "max_x": self.max_x,
                "min_y": self.min_y, "max_y": self.max_y}


@dataclass(frozen=True)
class GcodeTransform:
    """espejo opcional en Y, despues escala, despues traslacion, siempre en ese orden.
    asi espejar y ajustar al area se pueden componer en una sola instancia"""
    flip_y: bool = False
    flip_axis: float = 0.0      
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def apply(self, x: float, y: float) -> tuple:
        if self.flip_y:
            y = self.flip_axis - y
        return (x * self.scale + self.offset_x,
                y * self.scale + self.offset_y)

    @property
    def is_identity(self) -> bool:
        return (not self.flip_y and self.scale == 1.0
                and self.offset_x == 0.0 and self.offset_y == 0.0)

    def as_dict(self) -> dict:
        return {"flip_y": self.flip_y, "scale": round(self.scale, 6),
                "offset_x": round(self.offset_x, 4),
                "offset_y": round(self.offset_y, 4)}


IDENTITY = GcodeTransform()


def flip_y_about(bounds: Bounds) -> GcodeTransform:
    """espeja en Y alrededor del centro de la caja del dibujo, no de max_y_mm.
    asi el dibujo no se mueve ni se sale del area, la caja no cambia"""
    return GcodeTransform(flip_y=True, flip_axis=bounds.min_y + bounds.max_y)


def fit_to_area(bounds: Bounds, max_x: float, max_y: float,
                margin_mm: float = 1.0,
                base: GcodeTransform = IDENTITY) -> GcodeTransform:
    """escala, solo encoge, y centra el dibujo en el area util.
    base sirve para conservar un espejo ya activo sin recalcular nada"""
    usable_x = max(0.0, max_x - 2.0 * margin_mm)
    usable_y = max(0.0, max_y - 2.0 * margin_mm)

    scale_x = usable_x / bounds.width if bounds.width > 1e-9 else float('inf')
    scale_y = usable_y / bounds.height if bounds.height > 1e-9 else float('inf')
    scale = min(scale_x, scale_y, 1.0)      # nunca agranda, solo encoge
    if scale <= 0.0 or scale == float('inf'):
        scale = 1.0

    offset_x = margin_mm + (usable_x - bounds.width * scale) / 2.0 - bounds.min_x * scale
    offset_y = margin_mm + (usable_y - bounds.height * scale) / 2.0 - bounds.min_y * scale

    return GcodeTransform(flip_y=base.flip_y, flip_axis=base.flip_axis,
                          scale=scale, offset_x=offset_x, offset_y=offset_y)


def build(bounds: Bounds, max_x: float, max_y: float,
          flip_y: bool = False, fit: bool = False,
          margin_mm: float = 1.0) -> GcodeTransform:
    """lo que llama la api, siempre parte de la caja original, nunca
    encadena sobre la transformacion previa. si no, ajustar dos veces encogeria el dibujo"""
    t = flip_y_about(bounds) if flip_y else IDENTITY
    if fit:
        t = fit_to_area(bounds, max_x, max_y, margin_mm, base=t)
    return t
