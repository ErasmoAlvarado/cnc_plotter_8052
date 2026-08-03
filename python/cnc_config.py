"""
cnc_config.py — Configuracion persistente del Mini CNC Plotter — v2 FINAL

CAMBIOS RESPECTO A LA v1:
  [SW-6]  steps_per_mm_z: el eje Z tiene su propia escala. Antes el jog
          de Z usaba steps_per_mm_x, que no tiene nada que ver.
  [SW-2]  speed_z: velocidad propia del eje Z. Antes compartia VEL con
          X e Y y acababa corriendo a 2 ms/paso = stall garantizado.
  [SW-11] z_pen_down_threshold: umbral de Z del G-code. Muchisimos
          post-procesadores usan Z0 = pluma ABAJO; con el codigo viejo
          (z < 0) el dibujo salia en blanco.
  [SW-12] max_x_mm / max_y_mm coherentes (40.0). Antes el default era
          8.0 aqui, 40.0 en CNCPlotter y 80.0 en /api/status.
  [SW-45] speed_draw 3->5 y speed_rapid 2->6. Un 28BYJ-48 a 5 V (menos
          ~1 V de caida en la ULN2003) no tiene par util a 2 ms/paso.
  [SW-26] Escritura ATOMICA (tmp + os.replace) y validacion de rangos.
          Antes un JSON corrupto se tragaba en silencio y perdias todo.
  [SW-30] pen_invert: sentido fisico del eje Z. Segun como montes el
          porta-pluma, "arriba" en el software puede ser "abajo" en la
          realidad. Se empuja al firmware (C_ZDIR), no se emula aqui.
  [SW-31] Los booleanos ya no se validan con bool(val): bool("false")
          era True y un JSON editado a mano invertia el ajuste.
  [SW-32] z_pen_down_threshold entra en _RANGES: era el unico numero
          que llegaba al plotter sin sanear (un "abc" lo reventaba).
"""

import json
import os
import tempfile

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'cnc_config.json'))

DEFAULT_CONFIG = {
    # --- geometria ---
    "steps_per_mm_x": 170.67,       # 4096 pasos/rev / 24 mm de circunferencia
    "steps_per_mm_y": 170.67,
    "steps_per_mm_z": 100.0,        # NUEVO: el mecanismo Z casi nunca es igual
    "backlash_x": 0,
    "backlash_y": 0,
    "max_x_mm": 40.0,
    "max_y_mm": 40.0,

    # --- velocidades (ms entre medios pasos) ---
    "speed_draw": 5,                # X/Y dibujando
    "speed_rapid": 6,               # X/Y en rapido
    "speed_z": 8,                   # NUEVO: eje Z, el que pelea con la gravedad

    # --- pluma ---
    "pen_steps": 100,               # profundidad: pasos de Z entre arriba y abajo
    "z_pen_down_threshold": 0.0,    # NUEVO: G-code con Z <= esto => pluma abajo

    # [SW-30] Sentido fisico del eje Z. Si al montar el porta-pluma el
    # mecanismo queda al reves (el software dice "arriba" y la pluma baja),
    # pon esto en true. NO se emula en el PC: se envia al firmware con
    # C_ZDIR, que es quien invierte el giro. Asi Z_POS sigue significando
    # lo mismo (0 = arriba, pen_steps = abajo) y pen_up/pen_down siguen
    # siendo absolutos e idempotentes en los dos montajes.
    "pen_invert": False,

    # --- perspectiva del usuario ---
    # En que esquina ve el usuario el (0,0). Esta maquina tiene el origen
    # ARRIBA a la izquierda, y por eso invert_y viene activado de fabrica:
    # sin esto, el lienzo dibuja el origen abajo y la flecha "Arriba" del
    # D-pad mueve el cabezal hacia abajo en la realidad.
    #
    # OJO: esto NO toca la cinematica. Los pasos siguen siendo no negativos
    # y los mm siguen viviendo en [0, max_*]; meter el espejo en
    # mm_to_steps_y ataria el origen a max_y_mm (cambiar el tamano del area
    # moveria el cero) y obligaria a manejar pasos negativos en el backlash,
    # en .last_position y en el troceado de CMD_LINE. Es presentacion y
    # mapeo de las flechas, y vive en frontend/src/coords.js.
    "invert_x": False,
    "invert_y": True,

    # --- comportamiento ---
    # Bloquear los trabajos que se salen del area. La maquina no tiene
    # finales de carrera: llegar al tope pierde pasos y descalibra.
    "enforce_soft_limits": True,

    "last_calibration_date": None,
}

# (minimo, maximo) para sanear valores corruptos o absurdos
_RANGES = {
    "steps_per_mm_x": (1.0, 5000.0),
    "steps_per_mm_y": (1.0, 5000.0),
    "steps_per_mm_z": (1.0, 5000.0),
    "backlash_x": (0, 255),
    "backlash_y": (0, 255),
    "max_x_mm": (1.0, 1000.0),
    "max_y_mm": (1.0, 1000.0),
    "speed_draw": (2, 255),
    "speed_rapid": (2, 255),
    "speed_z": (4, 255),            # nunca por debajo de 4 ms: se pierde par
    "pen_steps": (1, 255),          # PEN_N es un byte en el firmware
    "z_pen_down_threshold": (-1000.0, 1000.0),   # [SW-32]
}

_INT_KEYS = {"backlash_x", "backlash_y", "speed_draw", "speed_rapid",
             "speed_z", "pen_steps"}

# Ultimo error de E/S, para que la API pueda avisar en vez de callarse
last_error = None

_TRUE_STRINGS = {"1", "true", "yes", "on", "si", "sí", "y", "t"}
_FALSE_STRINGS = {"0", "false", "no", "off", "n", "f", ""}


def get_config_path() -> str:
    return CONFIG_PATH


def _to_bool(val, default: bool) -> bool:
    """[SW-31] bool(val) no sirve: bool("false") es True, y este ajuste
    llega hasta el sentido de giro del eje Z. Un config editado a mano
    con "false" invertia la pluma al reves de lo que pedia el usuario."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in _TRUE_STRINGS:
            return True
        if s in _FALSE_STRINGS:
            return False
    return default


def _validate(cfg: dict) -> dict:
    """Fuerza tipos y rangos. Un valor invalido vuelve a su default en vez
    de propagarse hasta el firmware y provocar comportamiento raro."""
    out = DEFAULT_CONFIG.copy()
    for key, default in DEFAULT_CONFIG.items():
        val = cfg.get(key, default)
        if isinstance(default, bool):
            # antes que _RANGES: en Python bool es subclase de int
            val = _to_bool(val, default)
        elif key in _RANGES:
            lo, hi = _RANGES[key]
            try:
                val = int(val) if key in _INT_KEYS else float(val)
            except (TypeError, ValueError):
                val = default
            val = max(lo, min(hi, val))
        out[key] = val
    # conservar claves extra que no conocemos (compatibilidad hacia delante)
    for key, val in cfg.items():
        if key not in out:
            out[key] = val
    return out


def load_config() -> dict:
    global last_error
    last_error = None

    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("el JSON de config no es un objeto")
        return _validate(data)
    except Exception as e:
        # [SW-26] antes esto era 'except Exception: return DEFAULT' en
        # silencio absoluto. Ahora se conserva el motivo y se hace copia
        # del fichero roto para poder recuperar los valores a mano.
        last_error = f"{type(e).__name__}: {e}"
        try:
            os.replace(CONFIG_PATH, CONFIG_PATH + '.corrupto')
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> bool:
    """Fusiona `config` sobre lo que ya hay en disco y escribe de forma
    atomica. Devuelve True/False en vez de fallar en silencio."""
    global last_error
    last_error = None

    base = DEFAULT_CONFIG.copy()
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                base.update(existing)
    except Exception:
        pass  # fichero roto: partimos de los defaults

    base.update(config or {})
    final = _validate(base)

    tmp = None                           # definido ANTES del try: si falla
                                         # mkstemp, el except no puede dar
                                         # NameError al intentar limpiarlo
    try:
        directory = os.path.dirname(CONFIG_PATH) or '.'
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(final, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)     # atomico: nunca queda a medias
        return True
    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
        return False


def update_config(**kwargs) -> dict:
    """Atajo: actualiza claves sueltas y devuelve la config resultante."""
    save_config(kwargs)
    return load_config()
