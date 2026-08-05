# TODO — Frontend CNC Plotter (v1 básico)

Checklist simple para ir marcando el progreso. Cada sección corresponde a un área funcional.
No hace falta seguir el orden exacto, pero Conexión + Estado en vivo deben ir primero porque
todo lo demás depende de ellos.

## 0. Andamiaje del proyecto
- [x] `npm create vite@latest frontend -- --template react` en la raíz del repo
- [x] `cd frontend && npm install`
- [x] Confirmar que `npm run dev` levanta en http://localhost:5173
- [x] Fijar `server.port: 5173` en `vite.config.js`
- [x] Crear `src/api.js` con todas las funciones de la API (ver plan)
- [x] Crear `src/StatusContext.jsx` (polling + WebSocket + runAction)
- [x] Crear `src/styles.css` base (layout, colores de estado, disabled)
- [x] Armar `src/App.jsx` (header fijo + pestañas + banner de error)

## 1. Conexión
- [x] Selector de puerto serie + botón "Actualizar" (`/api/serial-ports`)
- [x] Checkbox "Modo simulación"
- [x] Botón Conectar / Desconectar con estados disabled correctos
- [x] Indicador de estado de conexión (punto de color)
- [x] Prompt de recuperación de posición (aceptar/reiniciar) tras conectar
- [x] Mostrar advertencia de firmware si `warning` viene en la respuesta de connect

## 2. Estado en vivo
- [x] Mostrar posición (mm y pasos)
- [x] Mostrar estado de la pluma (arriba/abajo)
- [x] Barra de progreso del job activo
- [x] Indicador de `comm_lost`
- [x] Lista de `warnings`
- [x] Botón "Detener" (siempre visible, habilitado solo si hay job activo)
- [x] Polling de `/api/status` cada ~1.5s cuando no hay job activo
- [x] Conexión WebSocket con reintento automático

## 3. G-code
- [x] Selector de archivo + botón "Subir"
- [x] Resumen: líneas totales, líneas de comando, cabe en área de trabajo, bounds
- [x] Aviso si `preview_truncated`
- [x] Vista previa SVG simple de `preview_paths`
- [x] Botón "Ejecutar" con mensaje explicando por qué está deshabilitado
- [x] Progreso en vivo durante la ejecución (via StatusBar/WS)

## 4. Patrones de prueba
- [x] Selector de patrón (square/triangle/circle/star/grid)
- [x] Input de tamaño con validación (0 < tamaño ≤ 1000)
- [x] Botón Ejecutar

## 5. Jog / Home
- [x] Input de distancia (mm) compartido
- [x] Botones X+/X-/Y+/Y-/Z+/Z-
- [x] Botón Home
- [x] Botón Fijar origen
- [x] Botón Motores off (X/Y)

## 6. Control de pluma
- [x] Subir / Bajar / Alternar
- [x] Pen-jog (pasos -255..255)
- [x] Fijar cero Z
- [x] Apagar Z (con advertencia visible de "requiere re-zero")
- [x] Ciclo de prueba (mostrar steps_lost)
- [x] Configurar profundidad de pluma (pen_steps 10-255)
- [x] Toggle de inversión de porta-pluma (deshabilitado + aviso si pen_invert_supported === false)

## 7. Velocidad
- [x] Inputs speed_draw / speed_rapid / speed_z
- [x] Texto de ayuda "menor número = más rápido"
- [x] Botones Recargar / Guardar (form local, no sobrescrito por polling)

## 8. Ajustes
- [x] Inputs steps_per_mm x/y/z
- [x] Inputs backlash x/y
- [x] Inputs área de trabajo max_x_mm / max_y_mm
- [x] Input umbral de pluma abajo (z_pen_down_threshold)
- [x] Checkbox forzar límites blandos
- [x] Botones Recargar / Guardar

## 9. Calibración
- [x] Sección pasos/mm: dibujar línea → input medido → aplicar (mostrar error%)
- [x] Sección backlash: mover → medir juego → aplicar
- [x] Sección pluma: instrucciones + enlace a la pestaña "Pluma"

## 10. Utilidades
- [x] Botón Resync
- [x] Botón Ping
- [x] Visor de configuración cruda (`/api/config`, JSON formateado)

## Regla global (verificar en cada panel)
- [x] Todos los controles que mueven la máquina se deshabilitan si `!status.connected` o `status.job?.active`
- [x] Subida de G-code solo requiere que no haya job activo (no requiere estar conectado)
- [x] Ejecutar (`/api/run`) requiere conectado + sin job + gcode cargado
- [x] Detener requiere job activo
- [x] Mensajes de error del backend (400/409/501/502) se muestran en el banner, no solo en consola

## Verificación manual (v1 — sin tests automatizados todavía)
- [ ] Terminal A: `python python/cnc_api.py` (elegir modo simulación si se solicita al iniciar)
- [ ] Terminal B: `cd frontend && npm run dev`, abrir http://localhost:5173
- [ ] Conectar en modo simulación, confirmar indicador verde y sin errores en consola
- [ ] Subir un G-code de prueba pequeño, revisar resumen y vista previa
- [ ] Ejecutar el G-code y confirmar barra de progreso vía WebSocket
- [ ] Detener un job a mitad de camino y confirmar que la pluma sube (finally del backend)
- [ ] Probar un patrón de prueba (square, tamaño pequeño)
- [ ] Probar jog en los 3 ejes, Home, Fijar origen, Motores off
- [ ] Probar todos los controles de pluma, incluida la advertencia de apagar Z
- [ ] Cambiar velocidades y ajustes, guardar, y confirmar (via Utilidades → ver config) que persisten
- [ ] Ejecutar el flujo de calibración de pasos/mm y de backlash con valores de prueba
- [ ] Probar Resync y Ping
- [ ] Confirmar que TODOS los controles relevantes quedan deshabilitados mientras un job está activo, y se re-habilitan al terminar
- [ ] Detener el proceso de `cnc_api.py` con el frontend abierto y confirmar que no crashea (banner de error + reintento de WS)

## v2 — rediseño de la interfaz (hecho)

La v1 de pestañas planas fue reemplazada por el dashboard + hojas modales descrito en
`DISENO_UI.md`. `src/api.js` y la mecánica de `src/StatusContext.jsx` se conservaron; todo lo
visual se reescribió.

- [x] Sistema de diseño propio (`src/theme/tokens.css` + `base.css`), claro y oscuro
- [x] Sprite de iconos propio (`public/icons.svg`) — el del template traía iconos de Bluesky/Discord
- [x] Primitivas reutilizables en `src/components/ui/` (Button, Card, Sheet, ConfirmDialog,
      SegmentedControl, Toggle, Stepper, Field, Banner, DisabledHint, Icon)
- [x] Franja superior pegajosa con conexión, posición, pluma, salud y Detener siempre accesible
- [x] Dashboard: jog pad + chips de paso + pluma + calibración + G-code + patrones
- [x] Lienzo con seguimiento en vivo (trazado completado + estela real + cabezal interpolado)
- [x] Reproducción en seco del dibujo ("Simular"), funciona sin máquina
- [x] Asistente de calibración en 3 pasos con avance bloqueado
- [x] Hoja de ajustes avanzados (velocidad, ajustes, pluma, diagnóstico)
- [x] Casos de borde: recuperación con minimapa, Z sin energizar, firmware sin C_ZDIR, comm_lost
- [x] `/api/upload-gcode` devuelve el índice de línea en cada trazo del preview (cambio en
      `python/cnc_api.py`) — es lo que permite pintar en vivo qué trazo se está dibujando

### Verificación hecha
- [x] `npm run lint` y `npm run build` sin errores
- [x] Backend en simulación: conectar, subir G-code, ejecutar y comprobar por WebSocket que
      llegan `progress` y `complete`; los trazos del preview traen `line` ascendente
- [x] Render de prueba del árbol completo y del lienzo (corte pendiente/dibujado, inversión
      de Y, estela solo con la pluma abajo, cabezal en su sitio)
- [x] Repaso visual en navegador — hecho ya sobre la v3 (ver más abajo)

## v3 — rediseño visual "instrumento" (hecho)

La v2 se veía como una imitación de Apple: todo cristal, cinco colores de sistema más luces
ambiente animadas, escala táctil de iOS en una app de ratón, y un documento centrado de
1180 px que dejaba ~700 px de vacío a cada lado en un monitor ancho. Ver `DISENO_UI.md`.

- [x] `src/theme/tokens.css` reescrito: rampa neutra, un solo acento, `light-dark()`, escala
      de escritorio, tres niveles de elevación, sin `--glow-*` ni luces de fondo
- [x] Tipografía empaquetada (Inter + JetBrains Mono variables) — antes caía en Segoe UI
- [x] Iconos de Lucide con un único grosor; solo `pen-up`/`pen-down` siguen siendo propios
- [x] Armazón `src/shell/` de 100dvh sin scroll de página: TopBar / Rail / Stage / StatusBar
- [x] El marco del lienzo toma la proporción del área de trabajo y absorbe todo el espacio
      libre (`--ratio` + unidades de contenedor)
- [x] `GcodeCard` partido: resumen y carga al rail, lienzo y ejecución al escenario, con el
      estado en `shell/useDrawing.js`
- [x] `Sheet`/`ConfirmDialog` sobre Radix (foco, scroll-lock, Escape) conservando su API
- [x] Movimiento con `motion`: resortes en los grupos del rail, el jog y el progreso
- [x] Corregido `vector-effect: non-scaling-stroke`, que nunca se aplicó (el selector
      `[stroke]` matchea el atributo, y el stroke lo pone la clase) — de ahí que la retícula
      del lienzo se viera como bandas gruesas
- [x] `useTheme` ahora escucha el cambio de tema del SO, no solo lo lee al montar

### Verificación hecha (v3)
- [x] `npm run lint` y `npm run build` sin errores nuevos
- [x] Repaso a 960 / 1280 / 1440 / 1600 / 2560 px: sin scroll de página ni horizontal, el
      lienzo crece visiblemente con el ancho, el rail cae a cajón por debajo de 1024
- [x] Claro y oscuro
- [x] Flujo completo en simulación: subir G-code, «Simular» (pintado progresivo), y pintado en
      vivo con mensajes `progress` reales inyectados por el WebSocket — barra de progreso,
      telemetría, insignia «Dibujando», trazos virando a acento y controles bloqueados con su
      motivo
- [x] Hojas de conexión, calibración y ajustes avanzados

## v4 — capa de movimiento (hecho)

El vocabulario de `motion.js` existía desde v3 pero estaba aplicado a medias: los botones del jog
respondían a la pulsación y «Ejecutar» no; el rail se desplegaba con física y el panel de dibujo
cambiaba de estado con un corte seco. La inconsistencia era el problema, no la falta de animación.

- [x] `useMotionPrefs()` en `motion.js`: un único sitio donde se atiende `prefers-reduced-motion`
      en JS, en vez del ternario copiado en cinco componentes
- [x] Variantes compartidas `fadeUp` / `fadeScale` / `collapse` / `stagger`; `collapse` unifica el
      despliegue que estaba duplicado palabra por palabra en `RailGroup` y `PenControl`
- [x] `spring.gentle`, que estaba declarado y sin usar, pasa a ser el resorte de los cambios de vista
- [x] `Button` es `motion.button` con `whileTap` — alcanza de una vez a los ~40 sitios que lo usan.
      Se quita `.btn:active { translateY(1px) }`, que motion pisaba de todos modos
- [x] `IconButton` nuevo: `TopBar`, `Sheet`, `Banner` y `Stepper` escribían su botón de icono a mano
      y por eso quedaban inertes
- [x] `ConfirmDialog` deja de escribir las clases `.btn` a mano y usa `Button` con `asChild`
- [x] Indicador deslizante en `SegmentedControl` con `layoutId` + `useId`
- [x] `Reveal` nuevo: las cajas de resultado de calibración y diagnóstico aparecen y **desaparecen**
      con animación (antes React desmontaba el nodo y se esfumaban)
- [x] Presencia en los cortes secos: escenario (insignia, leyenda ⇄ pista, barra flotante), barra de
      progreso ⇄ «En reposo», dropzone ⇄ ficha del archivo, hoja de conexión, secciones de ajustes,
      pasos del asistente (deslizamiento direccional: adelante y atrás no se ven igual)
- [x] `RecoveryDialog` montado siempre, con `open`: con `{recovery && …}` nunca podía animar su cierre
- [x] El porcentaje del progreso sale del mismo `MotionValue` que el relleno de la barra
- [x] Entrada escalonada del rail (40 ms) y fundido corto del armazón, solo al montar
- [x] Desenfoque del scrim animándose desde cero y hoja modal subiendo 6 px al entrar

### Verificación hecha (v4)
- [x] `npm run build` y `npm run lint` sin errores nuevos
- [ ] Repaso visual en simulación: pendiente de hacer con la interfaz delante (ver más abajo)

### Verificación pendiente (v4)
- [ ] Recorrido en simulación: conectar/desconectar, cargar G-code, ejecutar y parar a media
      ejecución, «Simular», jog en los tres ejes, ajuste fino de pluma
- [ ] Las cuatro secciones de ajustes avanzados y los tres pasos del asistente, hacia adelante y
      hacia atrás
- [ ] `prefers-reduced-motion` activado en el SO: todo debe cortar a instantáneo sin que nada quede
      invisible ni a medio camino (el fallo típico de un `AnimatePresence` mal puesto es un elemento
      que se queda en `opacity: 0`)
- [ ] Claro y oscuro, y anchos 1024 / 1440 / 2560 px incluido el cajón del rail
- [ ] La barra flotante del lienzo sigue centrada al entrar y al salir (su centrado ya no está en CSS)

## Pendientes (siguientes)
- [ ] Servir el frontend construido (`npm run build`) desde FastAPI — requiere decidir cómo separar
      el código fuente de Vite del `outDir` esperado (`frontend/index.html` directo), o cambiar el
      punto de montaje en el backend. No resuelto en v1: se usa `npm run dev` (puerto 5173) en su lugar.
- [ ] Extraer `API_BASE`/`WS_URL` a variables de entorno si el despliegue lo requiere
- [ ] Tests automatizados (Vitest + React Testing Library para componentes, Playwright para el flujo
      end-to-end contra `cnc_api.py --simulate`)
- [ ] TypeScript, si se decide adoptarlo
- [ ] Zoom y desplazamiento sobre el lienzo (hoy encuadra el área completa y no se puede acercar)
- [ ] Estimación de tiempo restante en la barra de progreso

## v5 — perspectiva, límites y ajuste de pluma (hecho)

La máquina dibujaba, pero el software no coincidía con lo que el usuario tiene delante: el origen
real está en la esquina **superior izquierda** y el lienzo lo pintaba abajo, así que el dibujo se
veía del revés y «Arriba» en el D-pad movía el cabezal hacia abajo. Y un G-code más grande que el
área se ejecutaba igual: sin finales de carrera, eso es perder pasos y quedarse sin calibración.

### Backend
- [x] `python/gcode_walk.py` — **un solo intérprete** de G-code. Antes había tres (ejecución,
      límites y preview) y ya divergían: los dos últimos se saltaban el viaje al origen de
      `G28`/`M2`/`M30`, y el preview ignoraba el estado de pluma que deja un `G0`
- [x] `python/gcode_parse.py` — el léxico y `arc_to_segments` salen de `cnc_plotter.py` (import
      circular); se re-exportan desde allí para no romper a nadie
- [x] `python/gcode_transform.py` — espejo en Y y «ajustar al área» como una afín inmutable.
      Los arcos se descomponen **antes** de transformarse, así que voltear no obliga a invertir
      G2↔G3 ni el signo de J
- [x] `python/soft_limits.py` — comprobación de punto y de caja, con violación estructurada
- [x] Los límites **bloquean**: pre-vuelo en `/api/run` y `/api/test-pattern` (409 con detalle),
      `_check_area` lanza `LimitExceeded`, `/api/jog` devuelve `max_allowed_mm`
- [x] `POST /api/gcode-transform {flip_y, fit}` — sin reescribir el fichero
- [x] `GET /api/patterns` — cuánto cabe de cada patrón (`size` es lado, radio o espaciado según cuál)
- [x] Calibración de pasos/mm **por eje**: `axis` en draw-line y apply
- [x] `POST /api/pen-test-line` — traza y vuelve, sin tocar el origen
- [x] `invert_x` / `invert_y` en la config, en `/api/settings` y en `/api/status`
- [x] `/api/settings` ya no exige conexión (el área y la perspectiva son presentación)
- [x] `python/tests/` con pytest: 51 tests. El importante es
      `test_lo_que_se_ejecuta_es_lo_que_se_valida`

### Frontend
- [x] `src/coords.js` — único dueño de la perspectiva: `projection()` para el lienzo,
      `jogVector()` para el D-pad, `blockedJogs()` para apagar la flecha que se saldría
- [x] El D-pad habla en direcciones que ve el usuario, no en ejes con signo
- [x] `ZControl` pasa a **pasos** (±1/±5) por `/api/pen-jog`: compartía el valor en mm de X/Y y con
      el chip de 10 mm el backend recortaba en silencio a 255 pasos
- [x] `DrawingPanel`: casilla «Voltear Y» y botón «Ajustar al área», con preview en vivo
- [x] `PatternsPanel`: los patrones que no entran quedan deshabilitados
- [x] `components/pen/PenTuner.jsx` — deslizador de presión de 1 en 1, probar arriba/abajo, línea de
      test y fijar el cero. Tres puertas: rail, paso 3 del asistente y ajustes avanzados
- [x] `components/calibration/QuickCalibration.jsx` — «Ajustes rápidos»: cada parámetro por separado
      sin recorrer el asistente entero
- [x] `hooks/useSyncedForm.js` — los campos se siembran cuando llega `status`. Antes
      `useState(status?.pen_steps)` con `status` a `null` dejaba el campo en el valor por defecto y
      «Guardar» escribía ese
- [x] Modales anidados: `ConfirmDialog` restaura el `pointer-events` del `<body>` si queda colgado.
      Era la causa de «el asistente se bloquea al pulsar botones» — no eran los botones, era que
      ningún clic llegaba a ninguna parte
- [x] `completed` se reinicia al reabrir el asistente, y ya no se puede saltar el paso 1
- [x] `setZEnergized(true)` solo en el camino de éxito
- [x] Estado `busy` en `runAction`: los botones de acciones serie se deshabilitan mientras dura
- [x] Rendimiento: `StatusContext` memoizado, `PlotHead` aparte (su interpolación a 60 fps
      re-renderizaba el SVG entero), `useTrailPath` incremental en un solo `<path>`, y el `d` de
      cada trazo se calcula una vez en vez de en cada mensaje del WebSocket

### Verificación hecha
- [x] `pytest` (51 en verde), `npm run build` y `npm run lint` sin errores nuevos
- [x] Contra el backend en simulación por HTTP: subida, bloqueo por área, «ajustar al área» y
      ejecución posterior, espejo en Y comprobado punto a punto y reversible, patrones fuera de
      rango rechazados con su máximo, jog con `max_allowed_mm`, calibración de Y sin tocar X,
      `/api/pen-test-line`

### Verificación pendiente
- [ ] Repaso en el navegador con la interfaz delante (no se pudo hacer en esta sesión: la extensión
      de Chrome no estaba conectada). En concreto: que el origen se pinte arriba a la izquierda,
      que «Arriba» mueva hacia arriba, y **que al cancelar el confirmador del porta-pluma dentro del
      asistente la página siga respondiendo a los clics**
- [ ] Perfil de rendimiento con un G-code de ~5000 trazos dibujando en simulación
- [ ] `prefers-reduced-motion` y claro/oscuro sobre los controles nuevos (deslizador, ajustes rápidos)
