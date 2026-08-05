import { useEffect } from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import Button from './Button.jsx'
import Icon from './Icon.jsx'

// bug conocido de radix: mientras hay un modal abierto pone pointer-events:
// none en el body (via react-remove-scroll) y lo saca al cerrar. con DOS
// modales anidados -- y aca pasa, este dialogo vive adentro de la hoja del
// wizard y de la de ajustes avanzados -- el que se cierra puede pisar la
// restauracion del que sigue abierto y la pagina entera deja de responder
// al mouse. esto era el bug raro de "el wizard se traba al apretar
// botones", no eran los botones, ningun click llegaba a ningun lado.
//
// al cerrar chequeamos si queda algun dialog abierto de verdad, si no
// queda ninguno y el body sigue con pointer-events apagado lo restauramos
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

// confirmacion para pasos que pueden costarle al usuario la calibracion o
// la pluma: apagar Z, invertir el porta-pluma, descartar la posicion
// recuperada. el mensaje describe la consecuencia fisica y no la operacion
// tecnica (la pluma se puede caer, no "se va a mandar CMD_ZOFF").
//
// uso AlertDialog y no Dialog porque un alert no se cierra clickeando
// afuera y el foco va directo al boton cancelar, que es lo que queres
// cuando lo de atras se puede romper
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
          {/* asChild y no clases .btn a mano, si no estos 2 botones (los mas
              visibles de un momento delicado) quedan afuera del componente
              Button y pierden su feedback de click y cualquier cambio futuro */}
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
