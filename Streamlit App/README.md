# Shark Tank G1 — versión Streamlit

Misma herramienta de calificación del Comité de Innovación, reconstruida en
Streamlit para poder publicarla en un enlace público que **cualquier VP
abre desde su celular sin necesidad de cuenta de Claude**.

## Qué se conservó del modelo (sin cambios)

- Los 4 criterios de calificación (1-5) y sus preguntas exactas.
- Los pesos del puntaje: 30% Impacto · 20% Beneficio-recursos · 30% Contribución estratégica · 20% Viabilidad.
- El corte de cuadrantes en 50/50 (fase piloto).
- Los 4 nombres de decisión: Priorizar / Resolver barreras / Banco de iniciativas / No priorizar.
- Los colores de marca Postobón (navy `#001b50`, cian `#00b2f0`) y el logo real.
- El mix de horizonte del portafolio vs. meta fija 50/30/20 (dato real se escribe a mano, igual que en la versión Claude).
- El botón de descargar Excel con el resumen para transcribir a Monday.com.

**Lo que NO es igual:** el diseño visual pixel a pixel (la tarjeta tipo
Kahoot, las animaciones). Streamlit tiene su propio sistema de componentes;
aquí se aplicó la marca (colores, tipografía, logo) sobre esos componentes,
pero no es una réplica exacta del artefacto de Claude.

**Ojo con las burbujas de fondo (`render_bubbles()`):** usan `position:fixed`,
igual que en el artefacto de Claude. No pude probar en ejecución real si
Streamlit envuelve el contenido en algún contenedor con `transform` que
cambie ese comportamiento (es un caso conocido en algunas versiones). Si al
correrla las burbujas no se ven fijas respecto a toda la pantalla, avísame
para ajustarlo.

## Cómo funciona el estado compartido

Los datos de la sesión (iniciativas, votos, decisiones) viven en memoria
mientras la app esté corriendo (`st.cache_resource`), compartidos entre
todos los que tengan el link abierto al mismo tiempo. Cada navegador se
actualiza solo cada 2 segundos (no es instantáneo como un websocket, pero es
casi en vivo). **Si la app se reinicia o "duerme"** (Streamlit Community
Cloud duerme las apps gratuitas tras un rato sin uso), los datos de la
sesión se pierden — no es almacenamiento permanente. Para el día del
Comité: abre la app un rato antes para que esté "despierta", y evita
recargar el servidor a mitad de sesión.

## Enlaces personalizados por VP

Igual que en la versión Claude, cada VP puede tener su propio link para no
tener que elegir su rol a mano:

```
https://<tu-app>.streamlit.app/?vp=tecnica_innovacion
https://<tu-app>.streamlit.app/?vp=generacion_demanda
https://<tu-app>.streamlit.app/?vp=logistica_fp
https://<tu-app>.streamlit.app/?vp=ventas
https://<tu-app>.streamlit.app/?vp=gestion_humana
https://<tu-app>.streamlit.app/?vp=administrativa_financiera
https://<tu-app>.streamlit.app/?vp=coe
https://<tu-app>.streamlit.app/?vp=juridica_ac
https://<tu-app>.streamlit.app/?vp=riesgos_cumplimiento
```

Para el facilitador **no hay enlace directo** — siempre hay que entrar por
"Selecciona tu rol" → "Soy el facilitador" → clave (`IDEAR`), aunque se
llegue con `?role=facilitador` en la URL. Es a propósito: evita que
cualquiera con el link controle la sesión.

A diferencia del artefacto de Claude, aquí el parámetro `?vp=` de la URL
**sí llega correctamente** a la app (no hay el problema de sandboxing que
tuvimos allá) — por eso los enlaces de VP deberían funcionar de una.

## Cómo publicarla en Streamlit Community Cloud (gratis)

1. Sube esta carpeta (`app.py`, `requirements.txt`, `assets/`) a un
   repositorio de GitHub (puede ser privado). Si no tienes uno, créalo en
   [github.com/new](https://github.com/new) y sube estos archivos ahí
   (arrastrando los archivos desde la web de GitHub, sin necesidad de usar
   la terminal).
2. Entra a [share.streamlit.io](https://share.streamlit.io) e inicia sesión
   (puedes hacerlo con tu cuenta de GitHub).
3. Clic en **"New app"** → selecciona el repositorio que acabas de crear →
   en "Main file path" pon `Streamlit App/app.py` (o la ruta donde haya
   quedado `app.py` dentro del repo) → **Deploy**.
4. En un par de minutos te da una URL pública tipo
   `https://<algo>.streamlit.app` — ese es el enlace que compartes con el
   Comité (con los `?vp=...` de arriba para cada VP).

Si prefieres que TI lo aloje en un servidor interno en vez de Community
Cloud, el mismo `app.py` funciona igual — solo cambia cómo se ejecuta
(`streamlit run app.py` en ese servidor).

## Correrla en tu computador para probar antes del evento

```bash
cd "Streamlit App"
pip install -r requirements.txt
streamlit run app.py
```

Esto abre la app en `http://localhost:8501` en tu navegador. Para probar
varios roles a la vez, abre varias pestañas con distintos `?vp=...`.
