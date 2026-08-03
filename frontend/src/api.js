// Unico punto de contacto con el backend FastAPI (python/cnc_api.py).
// Ningun componente debe llamar fetch()/WebSocket directamente: todo pasa por aca.

export const API_BASE = 'http://127.0.0.1:8000'
export const WS_URL = 'ws://127.0.0.1:8000/ws'

async function apiFetch(path, options = {}) {
  const isForm = options.body instanceof FormData
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: isForm
      ? options.headers
      : { 'Content-Type': 'application/json', ...options.headers },
  })

  let data = null
  try {
    data = await res.json()
  } catch {
    // cuerpo vacio, ej. algunas respuestas 204
  }

  if (!res.ok) {
    // Los errores de limites llegan como objeto y no como cadena, porque el
    // frontend necesita los datos ademas del texto (cuantos mm quedan, si se
    // puede ofrecer "Ajustar al area"). Aqui se separan: `message` para el
    // banner, `detail` para quien sepa que hacer con el.
    const detail = data?.detail ?? data?.message
    const message =
      typeof detail === 'string'
        ? detail
        : (detail?.message ?? `Error ${res.status}`)

    const err = new Error(message)
    err.status = res.status
    err.data = data
    err.detail = typeof detail === 'object' && detail !== null ? detail : null
    throw err
  }

  return data
}

function post(path, body) {
  return apiFetch(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export const api = {
  // Conexion / estado
  connect: (port, simulate) => post('/api/connect', { port: port || null, simulate: !!simulate }),
  disconnect: () => post('/api/disconnect'),
  getStatus: () => apiFetch('/api/status'),
  ping: () => post('/api/ping'),
  resync: () => post('/api/resync'),
  listPorts: () => apiFetch('/api/serial-ports'),
  getConfig: () => apiFetch('/api/config'),
  recoverPosition: (action) => post('/api/recover-position', { action }),

  // G-code
  uploadGcode: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiFetch('/api/upload-gcode', { method: 'POST', body: fd })
  },
  run: () => post('/api/run'),
  stop: () => post('/api/stop'),
  // Espejo en Y / ajuste al area sobre el G-code YA cargado. Devuelve el
  // preview nuevo, asi que el lienzo muestra lo que se va a dibujar antes de
  // confirmar. El fichero no se reescribe: quitar el espejo cuesta lo mismo
  // que ponerlo.
  gcodeTransform: (flip_y, fit) => post('/api/gcode-transform', { flip_y, fit }),

  // Posicion
  setOrigin: () => post('/api/set-origin'),
  home: () => post('/api/home'),
  motorsOff: () => post('/api/motors-off'),

  // Jog
  jog: (axis, direction, distance_mm) => post('/api/jog', { axis, direction, distance_mm }),

  // Pluma / eje Z
  pen: (action) => post('/api/pen', { action }),
  penJog: (steps) => post('/api/pen-jog', { steps }),
  penHolder: (invert) => post('/api/pen-holder', { invert }),
  zSetZero: () => post('/api/z-set-zero'),
  zOff: () => post('/api/z-off'),
  penTestCycle: () => post('/api/pen-test-cycle'),
  penTestLine: (length_mm = 20) => post('/api/pen-test-line', { length_mm }),
  penConfig: (pen_steps) => post('/api/pen-config', { pen_steps }),

  // Velocidad / ajustes
  settings: (payload) => post('/api/settings', payload),
  speed: (payload) => post('/api/speed', payload),

  // Patrones de prueba
  testPattern: (pattern, size) => post('/api/test-pattern', { pattern, size }),
  // Hasta que tamano cabe cada patron en el area actual. 'size' no significa
  // lo mismo en todos (radio en el circulo, espaciado en la rejilla), asi que
  // el maximo lo calcula el backend a partir de la misma tabla que valida.
  listPatterns: () => apiFetch('/api/patterns'),

  // Calibracion. X e Y se miden y se aplican por SEPARADO: son dos ejes
  // mecanicamente distintos y aplicar la medida de uno al otro dejaba siempre
  // uno de los dos mal calibrado.
  calibrateDrawLine: (axis = 'x') => post('/api/calibrate/steps/draw-line', { axis }),
  calibrateApplySteps: (measured_mm, axis = 'x') =>
    post('/api/calibrate/steps/apply', { axis, measured_mm }),
  calibrateBacklashMove: (axis, steps) => post('/api/calibrate/backlash/move', { axis, steps }),
  calibrateBacklashApply: (backlash_x, backlash_y) =>
    post('/api/calibrate/backlash/apply', { backlash_x, backlash_y }),
}

export function openStatusSocket({ onMessage, onOpen, onClose }) {
  const ws = new WebSocket(WS_URL)
  ws.onopen = onOpen
  ws.onmessage = (evt) => {
    try {
      onMessage(JSON.parse(evt.data))
    } catch {
      // mensaje malformado, se ignora
    }
  }
  ws.onclose = onClose
  ws.onerror = () => {
    // el evento close se dispara igual, no hace falta manejarlo aparte
  }
  return ws
}
