# Diseño de la interfaz — v3 ("instrumento")

Este documento describe **la interfaz que está implementada**. La v1 (pestañas planas) y la v2
(dashboard de tarjetas de cristal) ya no existen: el código está en `src/shell/` y
`src/components/`, sobre React 19 + Vite.

Prioridad que guió el diseño: **manipulación y calibración primero** — cualquiera tiene que
poder mover la máquina y calibrarla sin entender la API. Eso no cambió entre v2 y v3; lo que
cambió es cómo se ve y cómo se reparte el espacio.

## Por qué se rehízo la v2

La v2 buscaba "Apple moderno" y terminó siendo una imitación: cada superficie era cristal
translúcido con reflejo y halo, había cinco colores de sistema más tres luces ambiente
animadas de fondo, la escala tipográfica era la táctil de iOS (17 px de cuerpo, radios de
22 px) aplicada a una app de escritorio con ratón, y el layout era un documento centrado de
1180 px que scrolleaba — en un monitor de 2560 px, ~700 px de fondo vacío a cada lado con el
lienzo encerrado en una tarjeta que no podía crecer.

La v3 invierte el criterio: **la aplicación es una carcasa gris y el dibujo es lo único
saturado de la pantalla.**

## Las tres reglas del sistema (`src/theme/tokens.css`)

1. **Un solo acento.** Marca la acción primaria y la tinta del trazo. Nada más lo usa de
   decoración.
2. **El resto del color significa estado**: rojo = paro, ámbar = atención, verde = enlace
   vivo. El verde aparece **solo** en el LED de conexión — si tiñe también toggles y botones,
   deja de querer decir "la máquina responde".
3. **La elevación se hace con bordes y con la rampa de superficies.** Sombra y desenfoque
   quedan para lo que de verdad flota sobre el contenido: hojas, diálogos, tooltips y la barra
   del lienzo.

Detalles del sistema:

- Claro y oscuro se declaran juntos con `light-dark()`: un valor por token en vez de repetir
  la paleta tres veces. El interruptor manual (`useTheme.js`) solo cambia `color-scheme`.
- Tipografía empaquetada (`@fontsource-variable`): Inter para texto, JetBrains Mono para todo
  número que la máquina actualiza. La v2 pedía SF Pro y en Windows caía en Segoe UI, así que
  se veía en una tipografía que nadie había elegido.
- Escala de escritorio: cuerpo 13 px, radios 5–14 px, alturas de control 22/26/30/36.
- Iconos de Lucide (`src/components/ui/Icon.jsx`) con un único grosor de trazo. Los dos únicos
  propios son `pen-up`/`pen-down`, que son del dominio.

## El armazón (`src/shell/`)

Una rejilla de `100dvh` que ocupa la ventana exacta. **La página no scrollea nunca**: lo que
scrollea es el rail, por su cuenta.

```
┌──────────────────────────────────────────────┐
│ TopBar   conexión · X/Y/Z · progreso · parar │
├──────────────┬───────────────────────────────┤
│ Rail         │ Stage                         │
│ (ancho fijo, │ el lienzo se queda con TODO   │
│  scroll      │ el espacio que sobra          │
│  propio)     │                               │
├──────────────┴───────────────────────────────┤
│ StatusBar   parámetros · avisos · REAL/SIM   │
└──────────────────────────────────────────────┘
```

| Ancho | Comportamiento |
|---|---|
| < 1024 px | el rail pasa a ser un cajón sobre el lienzo |
| 1024–1439 | rail 300 px |
| 1440–1919 | rail 320 px |
| ≥ 1920 | rail 356 px |

El `.stage__frame` toma la **proporción del área de trabajo** (`--ratio`, calculado en
`Stage.jsx` con el mismo 6 % de aire que usa el `viewBox` de `PlotCanvas`) y crece con unidades
de contenedor hasta tocar el lado que primero se agote. Por eso el recuadro abraza el dibujo
en vez de ser una caja ancha con el trazado flotando en el medio.

- **`TopBar`** — `ConnectionPill` (LED + puerto), `PositionReadout` (X/Y en mono),
  `PenIndicator`, `JobProgressBar` con **Detener siempre montado**, tema y ajustes.
- **`Rail`** — grupos colapsables (`RailGroup`) en el orden del trabajo real: Dibujo →
  Posición → Pluma → Calibración → Patrones. Si un grupo está colapsado, su estado sigue a la
  vista en la marca de la derecha ("cargado", "pendiente"). Lo colapsado se recuerda en
  `localStorage`.
- **`Stage`** — el lienzo. Sin archivo cargado no muestra un hueco vacío: muestra el área de
  trabajo con el cabezal en su posición real, que es información útil igual.
- **`StatusBar`** — área, pasos/mm, juego, y los avisos en una línea que se despliega al
  pulsarla. El de "Z sin energizar" se despliega solo, porque mientras está la pluma puede
  estar cayéndose por gravedad.

## Movimiento (`src/motion.js`)

Tres resortes (`snappy`, `smooth`, `gentle`) y nada más. Se usa física y no `transition: 240ms`
porque un resorte responde al estado en que estaba la animación al interrumpirla: colapsar un
grupo a medio abrir sale de donde estaba, no de cero.

`snappy` es la pulsación, `smooth` los paneles y avisos, `gentle` los cambios de vista (secciones
de la hoja avanzada, pasos del asistente) — más lento porque lo que cambia es todo el contenido
del contenedor, y a la velocidad de un panel se lee como un parpadeo.

Junto a los resortes hay tres **variantes de presencia** (`fadeUp`, `fadeScale`, `collapse`) y el
escalonado del rail (`stagger`). Existen para que los quince sitios que aparecen y desaparecen no
inventen cada uno su propio desplazamiento de "más o menos ocho píxeles". `fadeUp` es asimétrico
a propósito: entra desde abajo y sale hacia arriba, que se lee como que el contenido avanza; entrar
y salir por el mismo lado se lee como un rebote.

`useMotionPrefs()` es el **único** sitio donde se atiende `prefers-reduced-motion` en JavaScript.
`base.css` apaga las animaciones CSS por su cuenta, pero no puede tocar las de motion, y repetir
`reduce ? { duration: 0 } : spring.x` en cada componente significaba que el que se olvidara rompía
la accesibilidad en silencio, sin que nada fallara.

**Ojo con el `transform`.** Motion compone un único `transform` en el estilo inline, así que gana
siempre a la hoja de estilos. Un elemento que se centraba con `transform: translateX(-50%)` en CSS
se va al borde en cuanto motion lo anima: el centrado tiene que viajar con la animación (`x: '-50%'`
en los tres estados). Le pasa a `.stage__toolbar` y a `.stage__hint`. Por lo mismo, el hundido del
botón ya no es `.btn:active { translateY(1px) }` sino `whileTap` con escala — hacia la pantalla, no
hacia abajo.

**El lienzo no se anima.** `PlotCanvas` se repinta cinco veces por segundo con hasta 5000
trazos; el suavizado del cabezal lo resuelve `useSmoothedPoint` con `requestAnimationFrame`.
Tampoco se pone `layout` ni `layoutId` dentro del escenario mientras hay un trabajo corriendo.

La barra de progreso sí se interpola con `useSpring` (llega en saltos de 0,3 % cada 200 ms), y el
porcentaje escrito al lado sale del **mismo** `MotionValue` que el relleno: en dos fuentes distintas
se contradecían a la vista. **La lectura de posición no se interpola**: un número que muestra dónde
está la máquina tiene que decir la última posición reportada, no una intermedia inventada. Se
estabiliza con cifras tabulares.

El fondo del control segmentado no se pinta con `[aria-selected]`: es un elemento propio que viaja
entre opciones con `layoutId` (único por instancia, vía `useId`). Cambiar de sección deja de ser
un parpadeo en dos sitios y pasa a ser una sola cosa que se mueve, que es lo que el usuario cree
que está haciendo al pulsar.

Las hojas modales siguen animándose en CSS sobre `[data-state]` (Radix retrasa el desmontaje hasta
que la animación termina). Lo que sí hace falta es que la hoja **siga montada**: `RecoveryDialog`
se renderizaba con `{recovery && …}` y por eso nunca llegaba a reproducir su salida.

## El lienzo (`src/components/canvas/`)

`PlotCanvas` pinta, de atrás hacia adelante: papel del área de trabajo → retícula → trazado
pendiente (gris; los rápidos punteados) → trazado dibujado (**acento**) → estela real
(posiciones reportadas por la máquina) → cabezal (aro si la pluma está arriba, relleno si toca
el papel).

Cómo sabe qué se dibujó ya: `/api/upload-gcode` devuelve el **índice de línea** en cada trazo
del preview, y el mensaje `progress` del WebSocket cuenta líneas sobre esa misma lista, así que
una búsqueda binaria (`completedPaths` en `shell/useDrawing.js`) da el corte exacto. Con un
backend anterior a ese campo el lienzo degrada a "solo estela" en vez de romperse.

Dos detalles que importan:

- Los hasta 5000 trazos se concatenan en cuatro strings `d` con `useMemo`; cada mensaje del
  WebSocket solo recalcula el corte.
- `vector-effect: non-scaling-stroke` se aplica con `.plot-canvas :is(path, line, rect, …)`.
  El selector de la v2 era `.plot-canvas [stroke]`, que en CSS matchea el **atributo** stroke
  — y aquí el stroke lo pone la clase, así que no matcheaba nada y el grosor se multiplicaba
  por la escala del `viewBox`.

`usePlotPlayback` recorre el mismo dibujo sin máquina (botón **Simular**).

## Hojas modales

`Sheet` y `ConfirmDialog` son Radix (`Dialog` / `AlertDialog`): la trampa de foco, el bloqueo
de scroll, Escape y la restauración del foco los pone la librería. La entrada y la salida se
animan con CSS sobre `[data-state]` — Radix retrasa el desmontaje hasta que la animación
termina, así que no hace falta `AnimatePresence` en los portales.

1. **Conexión** (`components/connection/`) — puerto, simulación, y `RecoveryDialog` con
   minimapa cuando hay una posición recuperable.
2. **Asistente de calibración** (`components/calibration/`) — tres pasos con avance bloqueado
   hasta completar el anterior. El paso 2 reutiliza el `JogPad` del rail pero cableado a
   `/api/calibrate/backlash/move`, **no** a `/api/jog`: el jog normal ya compensa el backlash,
   así que medir con él daría siempre cero.
3. **Ajustes avanzados** (`components/advanced/`) — Velocidad, Ajustes, Pluma y Diagnóstico.

## Reglas de interacción que no cambiaron

- **Un estado inválido no se puede pedir.** `DisabledHint` atenúa el bloque y explica el
  motivo; el motivo lo da un único helper (`reason()` en `StatusContext`), no cada panel por su
  cuenta — así ninguna vista se olvida de comprobar `comm_lost`.
- **El jog pad no repite al mantener pulsado.** Cada jog es una llamada serie bloqueante, y
  encolar repeticiones separa la posición mostrada de la real.
- **Los pasos peligrosos avisan antes de ejecutar**: apagar Z, invertir el porta-pluma, fijar
  el origen.
- **Etiquetas cortas con tooltip**, nunca cortas a secas: el rail es estrecho, pero "Ir al 0"
  sigue explicándose al posarse encima.

## Casos de borde resueltos visualmente

- **Recuperación de posición** — `RecoveryDialog` con minimapa (el mismo `PlotCanvas` en modo
  estático) y dos acciones.
- **Firmware sin soporte de inversión** — no un toggle apagado, sino una frase explicando que
  hay que reprogramar el AT89S52. Con soporte desconocido (`null`): "Conectá la máquina para
  saberlo".
- **Z sin energizar** — aviso persistente en el pie, desplegado por su cuenta, con acción
  directa al paso 3 del asistente.
- **Comunicación perdida** — LED rojo latiendo al doble de velocidad (la urgencia va en el
  ritmo, no solo en el color, que un daltónico no distingue del verde) y `reason()`
  deshabilita todo lo que mueva la máquina.
- **El dibujo no cabe** — etiqueta roja en el rail, aviso escrito, y el límite del área
  remarcado en rojo sobre el lienzo, que dice *dónde* se sale.
