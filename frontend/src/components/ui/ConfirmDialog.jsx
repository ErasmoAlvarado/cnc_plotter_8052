import { useEffect } from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import Button from './Button.jsx'
import Icon from './Icon.jsx'

// Mientras hay un modal abierto, Radix (via react-remove-scroll) pone
// `pointer-events: none` en el <body> y lo quita al cerrarse. Cuando hay DOS
// modales anidados —y aqui los hay: este confirmador vive dentro de la hoja del
// asistente y dentro de la de ajustes avanzados— el que se cierra puede
// llevarse por delante la restauracion del que sigue abierto, y la pagina se
// queda entera sin responder al raton. Es el sintoma que se veia como "el
// asistente se bloquea al pulsar botones": no era que los botones estuvieran
// deshabilitados, es que ningun clic llegaba a ninguna parte.
//
// Al cerrarse se comprueba si queda algun dialogo abierto de verdad; si no
// queda ninguno y el body sigue apagado, se restaura.
function useUnstickPointerEvents(open) {
  useEffect(() => {
    if (open) return undefined
    const id = requestAnimationFrame(() => {
      if (document.body.style.pointerEvents !== 'none') return
      const abierto = document.querySelector(
        '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]',
      )
      if (!abierto) document.body.style.pointerEvents = ''
    })
    return () => cancelAnimationFrame(id)
  }, [open])
}

// Confirmacion de los pasos que pueden costarle al usuario la calibracion o la
// pluma: apagar el eje Z, invertir el porta-pluma, descartar la posicion
// recuperada.
//
// El mensaje describe la CONSECUENCIA fisica, no la operacion tecnica: quien
// esta delante de la maquina necesita saber que la pluma puede caerse, no que
// se va a enviar CMD_ZOFF.
//
// AlertDialog y no Dialog: un alert no se cierra al hacer clic fuera y el foco
// entra en el boton de cancelar, que es justo el comportamiento que se quiere
// cuando lo que hay detras puede romper algo.
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Continuar',
  cancelLabel = 'Cancelar',
  destructive = false,
  icon = 'warning',
  onConfirm,
  onCancel,
}) {
  useUnstickPointerEvents(open)

  return (
    <AlertDialog.Root open={open} onOpenChange={(next) => !next && onCancel()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="scrim" />
        <AlertDialog.Content className="alert">
          <div className={`alert__icon ${destructive ? 'alert__icon--danger' : ''}`.trim()}>
            <Icon name={icon} size={18} />
          </div>
          <div className="alert__text">
            <AlertDialog.Title className="alert__title">{title}</AlertDialog.Title>
            {message && (
              <AlertDialog.Description className="alert__message">{message}</AlertDialog.Description>
            )}
          </div>
          {/* `asChild` y no las clases .btn escritas a mano: escribirlas dejaba
              a los dos botones mas visibles de un momento delicado fuera del
              componente Button, o sea sin su respuesta a la pulsacion y sin
              enterarse de cualquier cambio futuro de las jerarquias. */}
          <div className="alert__actions">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary">{cancelLabel}</Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button variant={destructive ? 'danger' : 'primary'} onClick={onConfirm}>
                {confirmLabel}
              </Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
