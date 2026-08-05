// coords de la maquina a coords de pantalla viven todas aca, no en cada componente
//
// va aca y no en mm_to_steps_y para no atar el cero a max_y_mm
export const PAD_RATIO = 0.06

// mismo valor que soft_limits.TOLERANCE_MM del backend
export const TOLERANCE_MM = 0.5

// pasa coords de la maquina a coords de SVG. son funciones puras
export function projection({ maxX, maxY, invertX = false, invertY = false }) {
  // si invertY ya apunta como el SVG, sino hay que reflejar
  const x = (mm) => (invertX ? maxX - mm : mm)
  const y = (mm) => (invertY ? mm : maxY - mm)
  return {
    x,
    y,
    origin: { cx: x(0), cy: y(0) },
    // id de esta proyeccion, para que useTrailPath invalide su cache
    key: `${maxX}:${maxY}:${invertX ? 1 : 0}:${invertY ? 1 : 0}`,
  }
}

// viewBox en mm + proporcion del marco
export function viewport({ maxX, maxY }) {
  const maxDim = Math.max(maxX, maxY)
  const pad = maxDim * PAD_RATIO
  return {
    pad,
    maxDim,
    viewBox: `${-pad} ${-pad} ${maxX + pad * 2} ${maxY + pad * 2}`,
    ratio: (maxX + pad * 2) / (maxY + pad * 2),
  }
}

// nombradas por lo que ve el usuario, no por el eje real
export const JOG_BUTTONS = ['up', 'down', 'left', 'right']

// que eje y sentido mover segun la flecha que ve el usuario
export function jogVector(button, { invertX = false, invertY = false } = {}) {
  switch (button) {
    case 'up':
      return { axis: 'y', direction: invertY ? -1 : 1 }
    case 'down':
      return { axis: 'y', direction: invertY ? 1 : -1 }
    case 'left':
      return { axis: 'x', direction: invertX ? 1 : -1 }
    case 'right':
      return { axis: 'x', direction: invertX ? -1 : 1 }
    default:
      return null
  }
}

// apaga el boton antes de apretarlo, el backend igual valida en serio
export function blockedJogs({ position, stepMm, area, invert = {}, enforce = true }) {
  if (!enforce || !position || !(stepMm > 0)) return new Set()

  const limites = { x: area?.max_x_mm, y: area?.max_y_mm }
  const actual = { x: position.x_mm, y: position.y_mm }
  const bloqueadas = new Set()

  for (const button of JOG_BUTTONS) {
    const { axis, direction } = jogVector(button, invert)
    const limite = limites[axis]
    const desde = actual[axis]
    if (typeof limite !== 'number' || typeof desde !== 'number') continue

    const futuro = desde + direction * stepMm
    if (futuro < -TOLERANCE_MM || futuro > limite + TOLERANCE_MM) {
      bloqueadas.add(button)
    }
  }
  return bloqueadas
}

export function originLabel({ invertX = false, invertY = false } = {}) {
  const vertical = invertY ? 'superior' : 'inferior'
  const horizontal = invertX ? 'derecha' : 'izquierda'
  return `esquina ${vertical} ${horizontal}`
}
