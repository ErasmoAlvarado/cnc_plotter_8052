// Unico dueno de la relacion entre las coordenadas de la maquina y lo que ve
// el usuario. Ningun componente debe calcular un `maxY - y` por su cuenta.
//
// ─────────────────────────────────────────────────────────────────────
// EL PROBLEMA QUE RESUELVE
// ─────────────────────────────────────────────────────────────────────
// Esta maquina tiene el origen fisico en la esquina SUPERIOR IZQUIERDA, y el
// software lo dibujaba abajo a la izquierda. Consecuencia: el lienzo mostraba
// el dibujo del reves y, peor, pulsar "Arriba" en el D-pad movia el cabezal
// hacia abajo en la realidad. Las dos cosas son el mismo error de perspectiva
// y por eso se arreglan en el mismo sitio.
//
// ─────────────────────────────────────────────────────────────────────
// POR QUE VIVE EN EL FRONTEND Y NO EN LA CINEMATICA
// ─────────────────────────────────────────────────────────────────────
// La maquina no tiene finales de carrera: el origen es donde el usuario lo
// fija con /api/set-origin. Meter el espejo en mm_to_steps_y ataria el cero a
// max_y_mm —cambiar el tamano del area moveria el origen— y obligaria a
// manejar pasos negativos en el backlash, en .last_position y en el troceado
// de CMD_LINE. Los mm siguen viviendo en [0, max] y los pasos siguen siendo
// no negativos; lo unico que cambia es COMO SE PINTA y HACIA DONDE MUEVE cada
// flecha. El backend guarda invert_x/invert_y y los reporta, nada mas.

// Aire alrededor del area util, como fraccion de la dimension mayor. Estaba
// escrito dos veces (PlotCanvas y Stage) con un comentario en cada sitio
// avisando de que si cambiaba uno habia que cambiar el otro.
export const PAD_RATIO = 0.06

// La misma tolerancia que soft_limits.TOLERANCE_MM en el backend: el redondeo
// mm->pasos deja decimas por fuera que no significan nada mecanicamente.
export const TOLERANCE_MM = 0.5

/**
 * Proyeccion de coordenadas de maquina (mm, Y hacia arriba, origen en 0,0) al
 * espacio del SVG (Y hacia abajo). Devuelve funciones puras.
 */
export function projection({ maxX, maxY, invertX = false, invertY = false }) {
  // El SVG crece hacia abajo. Con el origen ARRIBA a la izquierda (invertY),
  // la Y de la maquina y la del SVG apuntan al mismo lado y no hay que
  // voltear nada; con el origen abajo, hay que reflejar.
  const x = (mm) => (invertX ? maxX - mm : mm)
  const y = (mm) => (invertY ? mm : maxY - mm)
  return {
    x,
    y,
    // Donde cae el (0,0) en el lienzo: la esquina desde la que se mide todo.
    origin: { cx: x(0), cy: y(0) },
    // Identidad de esta proyeccion. Quien cachea geometria ya convertida
    // (useTrailPath) la necesita para saber cuando lo cacheado dejo de valer.
    key: `${maxX}:${maxY}:${invertX ? 1 : 0}:${invertY ? 1 : 0}`,
  }
}

/** Encuadre del lienzo: viewBox en milimetros y proporcion del marco. */
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

// Las cuatro flechas del D-pad, nombradas por lo que el usuario VE, no por el
// eje. Es la traduccion que faltaba: los botones codificaban el signo del eje
// directamente ('arriba' = Y positivo) y por eso invertir la perspectiva los
// dejaba al reves.
export const JOG_BUTTONS = ['up', 'down', 'left', 'right']

/**
 * Que eje y en que sentido mover para que el cabezal vaya hacia donde apunta
 * la flecha, tal como lo ve el usuario.
 */
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

/**
 * Que flechas del D-pad sacarian el cabezal del area util.
 *
 * Se calcula aqui para poder apagar la flecha en vez de dejar pulsar y
 * devolver un 400: la regla de diseno de la app es que un estado invalido no
 * deberia poder pedirse. El backend valida igualmente — esto es la capa
 * visual, no la de seguridad.
 */
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

/** Etiqueta legible de la esquina en la que el usuario ve el (0,0). */
export function originLabel({ invertX = false, invertY = false } = {}) {
  const vertical = invertY ? 'superior' : 'inferior'
  const horizontal = invertX ? 'derecha' : 'izquierda'
  return `esquina ${vertical} ${horizontal}`
}
