"""
config persistente del plotter, se guarda en cnc_config.json en la raiz.
si no existe se crea sola con DEFAULT_CONFIG.

steps_per_mm_z va aparte de x/y porque el mecanismo del eje Z es distinto.
speed_z tampoco comparte velocidad con x/y: el 28BYJ-48 pierde par si va rapido.
"""

import json
import os
import tempfile

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'cnc_config.json'))

DEFAULT_CONFIG = {
    "steps_per_mm_x": 170.67,       # 4096 pasos por revolucion, 24mm de circunferencia
    "steps_per_mm_y": 170.67,
    "steps_per_mm_z": 100.0,
    "backlash_x": 0,
    "backlash_y": 0,
    "max_x_mm": 40.0,
    "max_y_mm": 40.0,

    "speed_draw": 5,
    "speed_rapid": 6,
    "speed_z": 8,

    "pen_steps": 100,               
    "z_pen_down_threshold": 0.0,    


    "pen_invert": False,


    "invert_x": False,
    "invert_y": True,

    "enforce_soft_limits": True,

    "last_calibration_date": None,
}

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
    "speed_z": (4, 255),            
    "pen_steps": (1, 255),         
    "z_pen_down_threshold": (-1000.0, 1000.0),
}

_INT_KEYS = {"backlash_x", "backlash_y", "speed_draw", "speed_rapid",
             "speed_z", "pen_steps"}

last_error = None

_TRUE_STRINGS = {"1", "true", "yes", "on", "si", "sí", "y", "t"}
_FALSE_STRINGS = {"0", "false", "no", "off", "n", "f", ""}


def get_config_path() -> str:
    return CONFIG_PATH


def _to_bool(val, default: bool) -> bool:
    """bool de un string no alcanza, bool de "false" da True igual.
    eso invertiria el giro de Z si alguien edita el json a mano."""
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
    """fuerza tipos y rangos, si algo viene invalido se cae al default en
    vez de llegar asi hasta el firmware"""
    out = DEFAULT_CONFIG.copy()
    for key, default in DEFAULT_CONFIG.items():
        val = cfg.get(key, default)
        if isinstance(default, bool):
            val = _to_bool(val, default)
        elif key in _RANGES:
            lo, hi = _RANGES[key]
            try:
                val = int(val) if key in _INT_KEYS else float(val)
            except (TypeError, ValueError):
                val = default
            val = max(lo, min(hi, val))
        out[key] = val
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
        last_error = f"{type(e).__name__}: {e}"
        try:
            os.replace(CONFIG_PATH, CONFIG_PATH + '.corrupto')
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> bool:
    """mergea config sobre lo que hay en disco, escribe atomico con tmp y replace.
    devuelve True o False en vez de explotar"""
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
        pass  

    base.update(config or {})
    final = _validate(base)

    tmp = None                     
    try:
        directory = os.path.dirname(CONFIG_PATH) or '.'
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(final, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)   
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
    """atajo para actualizar un par de claves sueltas y devolver la config"""
    save_config(kwargs)
    return load_config()
