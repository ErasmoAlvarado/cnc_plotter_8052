// todo con springs, no duraciones sueltas: un spring sigue desde donde
// estaba si lo interrumpis
//
// el canvas no usa esto, tiene su propio suavizado en useSmoothedPoint

import { useMemo } from 'react'
import { useReducedMotion } from 'motion/react'

export const spring = {
  // click/tap, entra y vuelve casi al toque
  snappy: { type: 'spring', stiffness: 560, damping: 34, mass: 0.5 },
  // paneles y grupos del rail
  smooth: { type: 'spring', stiffness: 300, damping: 32, mass: 0.8 },
  // cambios de vista, mas lento para no verse como un parpadeo
  gentle: { type: 'spring', stiffness: 180, damping: 26 },
}

// para valores del websocket, mas blando para que fluya entre muestras
export const readoutSpring = { stiffness: 130, damping: 24, mass: 0.5 }

// variantes de aparicion para avisos, fichas y cajas de resultado

// entra desde abajo y sale arriba para no verse como rebote
export const fadeUp = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
}

// aparece en su lugar, arranca en 0.96 para no verse como un salto
export const fadeScale = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.96 },
}

// despliegue vertical, quien lo use necesita overflow:hidden o se desborda
export const collapse = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1 },
  exit: { height: 0, opacity: 0 },
}

// entrada escalonada del rail, 40ms entre grupo para que se lea como lista
export const stagger = {
  parent: { hidden: {}, shown: { transition: { staggerChildren: 0.04 } } },
  child: { hidden: { opacity: 0, y: 6 }, shown: { opacity: 1, y: 0 } },
}

// base.css no toca las animaciones de motion, hay que apagarlas a mano
export function useMotionPrefs() {
  const reduce = useReducedMotion()

  return useMemo(
    () => ({
      // booleano crudo, para cuando no es una transicion animada
      reduce,
      // envuelve un spring, usar t en vez del ternario
      t: (value = spring.smooth) => (reduce ? { duration: 0 } : value),
      // feedback de tap, devuelve undefined para que motion ni monte el gesto
      tap: (scale = 0.97) => (reduce ? undefined : { scale }),
    }),
    [reduce],
  )
}
