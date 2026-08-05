// unico punto de contacto con el backend, nada de fetch suelto en componentes

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
    // algunas respuestas vienen sin body, 204
  }

  if (!res.ok) {
    // errores de limites vienen como objeto, el front necesita los datos ademas del texto
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
  connect: (port, simulate) => post('/api/connect', { port: port || null, simulate: !!simulate }),
  disconnect: () => post('/api/disconnect'),
  getStatus: () => apiFetch('/api/status'),
  ping: () => post('/api/ping'),
  resync: () => post('/api/resync'),
  listPorts: () => apiFetch('/api/serial-ports'),
  getConfig: () => apiFetch('/api/config'),
  recoverPosition: (action) => post('/api/recover-position', { action }),

  uploadGcode: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiFetch('/api/upload-gcode', { method: 'POST', body: fd })
  },
  run: () => post('/api/run'),
  stop: () => post('/api/stop'),
  // no reescribe el archivo, por eso sacar el espejo cuesta igual que ponerlo
  gcodeTransform: (flip_y, fit) => post('/api/gcode-transform', { flip_y, fit }),

  setOrigin: () => post('/api/set-origin'),
  home: () => post('/api/home'),
  motorsOff: () => post('/api/motors-off'),

  jog: (axis, direction, distance_mm) => post('/api/jog', { axis, direction, distance_mm }),

  pen: (action) => post('/api/pen', { action }),
  penJog: (steps) => post('/api/pen-jog', { steps }),
  penHolder: (invert) => post('/api/pen-holder', { invert }),
  zSetZero: () => post('/api/z-set-zero'),
  zOff: () => post('/api/z-off'),
  penTestCycle: () => post('/api/pen-test-cycle'),
  penTestLine: (length_mm = 20) => post('/api/pen-test-line', { length_mm }),
  penConfig: (pen_steps) => post('/api/pen-config', { pen_steps }),

  settings: (payload) => post('/api/settings', payload),
  speed: (payload) => post('/api/speed', payload),

  testPattern: (pattern, size) => post('/api/test-pattern', { pattern, size }),
  // size significa algo distinto por patron, el maximo lo calcula el backend
  listPatterns: () => apiFetch('/api/patterns'),

  // X e Y son ejes distintos, aplicar la medida de uno al otro dejaba uno mal calibrado
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
    // igual dispara el close despues, no hace falta hacer nada aca
  }
  return ws
}
