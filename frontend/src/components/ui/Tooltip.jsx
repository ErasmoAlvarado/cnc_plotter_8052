import * as T from '@radix-ui/react-tooltip'

// tooltip. es lo que permite que el rail sea denso sin volverse adivinanza,
// un boton de icono puede medir 26px si al pasar el mouse dice que hace.
//
// no reemplaza el aria-label, radix ya expone el contenido al lector de
// pantalla pero un tooltip nunca aparece con navegacion tactil, entonces
// todo control que solo se explica por aca tiene ademas su etiqueta accesible

export function TooltipProvider({ children }) {
  return (
    <T.Provider delayDuration={450} skipDelayDuration={250}>
      {children}
    </T.Provider>
  )
}

export default function Tooltip({ label, side = 'right', children }) {
  if (!label) return children

  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content className="tooltip" side={side} sideOffset={6} collisionPadding={8}>
          {label}
          <T.Arrow className="tooltip__arrow" width={9} height={4} />
        </T.Content>
      </T.Portal>
    </T.Root>
  )
}
