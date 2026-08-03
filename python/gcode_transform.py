"""
gcode_transform.py — Transformacion afin aplicada a la geometria de un G-code.

Existe para dos cosas que el usuario pide sobre un fichero YA cargado, sin
tocar el fichero ni volver a subirlo:

  - "Voltear Y": el G-code estandar asume Y hacia arriba (origen abajo a la
    izquierda). Esta maquina trabaja con el origen ARRIBA a la izquierda, asi
    que un fichero salido de un CAM normal se dibuja del reves. La casilla de
    la interfaz activa el espejo.

  - "Ajustar al area": el dibujo no cabe en el area util. En vez de bloquear y
    dejar al usuario buscandose la vida, se escala y se centra dentro de los
    limites.

TODO ocurre en milimetros del espacio del G-code. La conversion a pasos sigue
viviendo en CNCPlotter.mm_to_steps_x/_y y no se entera de nada de esto.

────────────────────────────────────────────────────────────────────────
POR QUE EL ESPEJO ES SEGURO AQUI Y NO LO SERIA REESCRIBIENDO EL G-CODE
────────────────────────────────────────────────────────────────────────
El fallo clasico al voltear Y es olvidar que un arco tambien se voltea: G2
(horario) pasa a ser G3 (antihorario) y la J cambia de signo. Quien reescribe
texto de G-code tiene que acordarse de las tres cosas, y si falla una, el arco
sale como su reflejo concavo sin que nadie lo note hasta ver el papel.

Aqui no puede pasar: gcode_walk.walk() PRIMERO descompone el arco en puntos
(arc_to_segments) y DESPUES pasa cada punto por esta transformacion. Espejar
una polilinea da la polilinea espejada, sin casos especiales. Por eso este
modulo solo necesita apply(x, y) y no sabe que existen los arcos.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    """Caja delimitadora en mm. Inmutable: se recalcula, no se muta."""
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
    """Espejo opcional en Y, despues escala uniforme, despues traslacion.

    El orden importa y es siempre este:
        y1 = flip_axis - y        (si flip_y)
        x2 = x  * scale + offset_x
        y2 = y1 * scale + offset_y

    Con ese orden, espejar y ajustar al area se pueden componer en UNA sola
    instancia — que es justo lo que hace falta cuando el usuario marca las dos
    opciones a la vez.
    """
    flip_y: bool = False
    flip_axis: float = 0.0      # y -> flip_axis - y, en el espacio de origen
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
    """Espejo en Y alrededor del centro de la PROPIA caja del dibujo.

    Alrededor de la caja del dibujo y no de max_y_mm a proposito: asi el
    dibujo se queda exactamente donde estaba y voltear nunca puede empujarlo
    fuera del area. Ademas deja la caja delimitadora intacta, lo que permite
    calcular el ajuste al area sin importar si hay espejo o no.
    """
    return GcodeTransform(flip_y=True, flip_axis=bounds.min_y + bounds.max_y)


def fit_to_area(bounds: Bounds, max_x: float, max_y: float,
                margin_mm: float = 1.0,
                base: GcodeTransform = IDENTITY) -> GcodeTransform:
    """Escala (nunca agranda) y centra el dibujo dentro del area util.

    `base` permite conservar un espejo ya activo: como flip_y_about() no
    cambia la caja delimitadora, la escala y el centrado salen iguales con
    espejo o sin el, y basta con copiar los campos del espejo.
    """
    usable_x = max(0.0, max_x - 2.0 * margin_mm)
    usable_y = max(0.0, max_y - 2.0 * margin_mm)

    # Un dibujo de ancho o alto cero (una linea recta) es legitimo: no se
    # escala por ese eje, solo se traslada.
    scale_x = usable_x / bounds.width if bounds.width > 1e-9 else float('inf')
    scale_y = usable_y / bounds.height if bounds.height > 1e-9 else float('inf')
    scale = min(scale_x, scale_y, 1.0)      # solo encoge, nunca amplia
    if scale <= 0.0 or scale == float('inf'):
        scale = 1.0

    # Centrado dentro del area util, ya en el espacio de destino.
    offset_x = margin_mm + (usable_x - bounds.width * scale) / 2.0 - bounds.min_x * scale
    offset_y = margin_mm + (usable_y - bounds.height * scale) / 2.0 - bounds.min_y * scale

    return GcodeTransform(flip_y=base.flip_y, flip_axis=base.flip_axis,
                          scale=scale, offset_x=offset_x, offset_y=offset_y)


def build(bounds: Bounds, max_x: float, max_y: float,
          flip_y: bool = False, fit: bool = False,
          margin_mm: float = 1.0) -> GcodeTransform:
    """Punto unico de construccion: lo que llama la API.

    Se calcula siempre desde la caja ORIGINAL del fichero, nunca encadenando
    sobre la transformacion anterior. Encadenar haria que pulsar "Ajustar al
    area" dos veces encogiera el dibujo dos veces.
    """
    t = flip_y_about(bounds) if flip_y else IDENTITY
    if fit:
        t = fit_to_area(bounds, max_x, max_y, margin_mm, base=t)
    return t
