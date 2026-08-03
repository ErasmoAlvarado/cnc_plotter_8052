// Vocabulario de movimiento.
//
// Tres resortes y ninguna duracion suelta. La razon de usar fisica y no
// `transition: 240ms ease` es que un resorte responde al estado en el que
// estaba la animacion cuando se la interrumpe: si el usuario colapsa un grupo a
// medio abrir, la altura sale de donde estaba, no de cero. Es la diferencia
// entre una interfaz que se siente viva y una que se siente programada.
//
// Lo que NO se anima con esto: el lienzo. PlotCanvas se repinta cinco veces por
// segundo con hasta 5000 trazos, y el suavizado del cabezal ya lo resuelve
// useSmoothedPoint con requestAnimationFrame.

import { useMemo } from 'react'
import { useReducedMotion } from 'motion/react'

export const spring = {
  // Feedback de pulsacion: sale y vuelve casi de inmediato.
  snappy: { type: 'spring', stiffness: 560, damping: 34, mass: 0.5 },
  // Paneles y grupos del rail.
  smooth: { type: 'spring', stiffness: 300, damping: 32, mass: 0.8 },
  // Cambios de vista: secciones de la hoja avanzada, pasos del asistente. Mas
  // lento a proposito — lo que cambia es TODO el contenido del contenedor, y a
  // la velocidad de un panel el cambio se lee como un parpadeo.
  gentle: { type: 'spring', stiffness: 180, damping: 26 },
}

// Para useSpring sobre numeros que llegan del WebSocket (progreso, telemetria).
// Mas blando que los de arriba a proposito: la muestra llega cada ~200 ms y lo
// que se busca es que el valor fluya entre muestras, no que rebote.
export const readoutSpring = { stiffness: 130, damping: 24, mass: 0.5 }

// ── Variantes de presencia ──────────────────────────────────────────────
//
// Lo que aparece y desaparece en esta app son avisos, fichas y cajas de
// resultado. Sin un juego comun cada sitio se inventa sus valores y quince
// desplazamientos de "mas o menos ocho pixeles" no son un sistema.
//
// El desplazamiento es corto (6px) y ASIMETRICO: entra subiendo desde abajo y
// sale hacia arriba. Entrar y salir por el mismo lado se lee como un rebote;
// asi se lee como que el contenido avanza.

export const fadeUp = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
}

// Para lo que aparece en el sitio en vez de llegar de fuera: la insignia
// "Dibujando", las pildoras de estado. La escala arranca en 0.96 y no en 0.8
// porque a mas recorrido deja de parecer que algo se enciende y empieza a
// parecer que algo salta.
export const fadeScale = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.96 },
}

// Despliegue vertical. Estaba escrito dos veces palabra por palabra (el grupo
// del rail y el ajuste fino de la pluma). Quien lo use tiene que poner
// `overflow: hidden` en el elemento, o el contenido se sale mientras la altura
// todavia esta creciendo.
export const collapse = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1 },
  exit: { height: 0, opacity: 0 },
}

// Entrada escalonada del rail, solo al abrir la aplicacion. Los cinco grupos
// apareciendo a la vez son un bloque que se enciende; con 40 ms entre uno y otro
// se leen como una lista, que es lo que son. Mas separacion y la app tarda en
// estar lista; menos y no se distingue de la aparicion simultanea.
export const stagger = {
  parent: { hidden: {}, shown: { transition: { staggerChildren: 0.04 } } },
  child: { hidden: { opacity: 0, y: 6 }, shown: { opacity: 1, y: 0 } },
}

// ── Preferencias ────────────────────────────────────────────────────────
//
// base.css apaga las animaciones CSS cuando el sistema pide menos movimiento,
// pero no puede tocar las de motion: esas son JavaScript y hay que atenderlas a
// mano. Antes eso significaba repetir `reduce ? { duration: 0 } : spring.x` en
// cada componente, y el que se olvidara rompia la accesibilidad en silencio sin
// que nada fallara. Este hook es el unico sitio donde vive esa decision.
export function useMotionPrefs() {
  const reduce = useReducedMotion()

  return useMemo(
    () => ({
      // El booleano crudo, para lo que no es una transicion: saltar un
      // MotionValue con .jump() en vez de animarlo con .set().
      reduce,
      // Envuelve un resorte. `t(spring.smooth)` en vez del ternario.
      t: (value = spring.smooth) => (reduce ? { duration: 0 } : value),
      // Feedback de pulsacion. Devuelve undefined —y no { scale: 1 }— para que
      // motion no llegue a montar el gesto.
      tap: (scale = 0.97) => (reduce ? undefined : { scale }),
    }),
    [reduce],
  )
}
