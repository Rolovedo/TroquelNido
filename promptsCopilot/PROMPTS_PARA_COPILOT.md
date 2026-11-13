# Prompts para el agente de Copilot (pégalos en orden, uno por vez)

Antes de empezar: abre la carpeta del proyecto, copia `nido_core.py`, `app.py`, la guía y la carpeta `.github/`. Adjunta con `#file` los que el prompt mencione.

## Prompt 1 – Entender el proyecto (sin cambiar nada)
Lee #file:.github/copilot-instructions.md, #file:nido_core.py y #file:app.py. Resume en 10 líneas cómo funciona el cálculo del troquel y qué falta para una versión web. No modifiques archivos todavía.

## Prompt 2 – Pruebas
Crea tests/test_core.py con pytest para nido_core.py: (a) base = dimensión + 2·margen, (b) ancho_total igual a la suma de las columnas, (c) valores nunca negativos, (d) advertencia cuando el troquel no cabe en la hoja, (e) error con dimensiones fuera de rango. Ejecuta las pruebas y corrige lo que falle.

## Prompt 3 – API
Agrega una API con FastAPI en api.py: POST /troquel recibe tipo, material, largo, ancho, alto, peso (opcional) y devuelve JSON con medidas, pasos y el SVG. GET /opciones devuelve los tipos y materiales válidos. Reutiliza nido_core sin duplicar lógica. Incluye requirements.txt.

## Prompt 4 – Frontend
Crea web/index.html con formulario (listas de tipo y material, campos numéricos), botón Generar, vista previa del SVG, lista de pasos y botón para descargar SVG. Consume la API. Diseño simple, responsive, en español.

## Prompt 5 – Exportación
Agrega exportación a PNG y a PDF a escala 1:1 (1 unidad = 1 mm) y un botón de descarga para cada una.

## Prompt 6 – Calibración con la prueba de caída
Mueve HOLGURAS y FLAUTAS a un archivo config.json editable, y agrega un campo opcional para sobrescribir g, d y flauta desde el formulario.

## Consejos
- Modo Agent para tareas que tocan varios archivos; Ask para preguntas.
- Después de cada prompt: ejecuta, prueba, y haz commit (`git commit -m "..."`).
- Si el agente cambia una fórmula, pídele que explique por qué y revisa contra la guía.
