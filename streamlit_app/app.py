"""
Shark Tank G1 — Comité de Innovación (Postobón)
Versión Streamlit — misma lógica y parametrización del modelo que la versión
construida como Artifact de Claude (criterios, pesos, cortes de cuadrante,
colores de marca, etiquetas). Pensada para publicarse en Streamlit Community
Cloud, con un enlace público que los VPs abren sin necesidad de cuenta.

Estado compartido: vive en memoria mientras la app esté corriendo (se pierde
si la app se reinicia/duerme). Suficiente para una sesión en vivo de un día;
no es almacenamiento permanente.
"""

import base64
import html
import time
import threading
from io import BytesIO
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Shark Tank G1 — Comité de Innovación", layout="centered")

# ============================================================
# PARAMETRIZACIÓN DEL MODELO — idéntica a la versión Claude
# ============================================================
VPS = [
    {"id": "tecnica_innovacion", "name": "VP Técnica e Innovación"},
    {"id": "generacion_demanda", "name": "VP Generación Demanda"},
    {"id": "logistica_fp", "name": "VP Logística y FP"},
    {"id": "ventas", "name": "VP Ventas"},
    {"id": "gestion_humana", "name": "VP Gestión Humana"},
    {"id": "administrativa_financiera", "name": "VP Administrativa y Financiera"},
    {"id": "coe", "name": "COE"},
    {"id": "juridica_ac", "name": "VP Jurídica y AC"},
    {"id": "riesgos_cumplimiento", "name": "Gestión Riesgos y Cumplimiento"},
]

TIPOS = ["Producto", "Proceso", "Canales", "Modelo de negocio", "Experiencia de usuario"]

CRITERIA = [
    {
        "name": "Impacto potencial",
        "q": "¿Cuál es la magnitud del impacto esperado para Postobón?",
        "accent": "#00b2f0",
        "opts": ["Limitado", "", "Relevante", "", "Altamente significativo"],
    },
    {
        "name": "Relación beneficio–recursos",
        "q": "¿En qué medida los beneficios esperados justifican la inversión, el tiempo y los demás recursos requeridos?",
        "accent": "#9d5fc4",
        "opts": ["No justifican", "", "Razonablemente", "", "Ampliamente"],
    },
    {
        "name": "Contribución estratégica",
        "q": "¿En qué medida la iniciativa contribuye a las prioridades estratégicas de Postobón?",
        "accent": "#e563a0",
        "opts": ["Limitada", "", "Parcial", "", "Directa y significativa"],
    },
    {
        "name": "Viabilidad",
        "q": "¿Qué tan factible es implementar la iniciativa, considerando su complejidad y el acceso a las capacidades requeridas?",
        "accent": "#ffc233",
        "opts": ["Barreras importantes", "", "Viable con ajustes", "", "Ruta clara y viable"],
    },
]

DECISIONES = [
    {"id": "avanza", "label": "Priorizar", "color": "#2CB1AE"},
    {"id": "resolver", "label": "Resolver barreras", "color": "#FFD347"},
    {"id": "banco", "label": "Banco de iniciativas", "color": "#3182D3"},
    {"id": "no_prioriza", "label": "No priorizar", "color": "#FF4382"},
]

QUAD_META = {
    "avanza": {"label": "Priorizar", "bg": "#C1F0F0", "text": "#2CB1AE"},
    "resolver": {"label": "Resolver barreras", "bg": "#FFF9E6", "text": "#FFD347"},
    "banco": {"label": "Banco de iniciativas", "bg": "#CADFF4", "text": "#3182D3"},
    "no_prioriza": {"label": "No priorizar", "bg": "#FFD1E0", "text": "#FF4382"},
}

NAVY_900 = "#000D27"
NAVY_CARD = "#142038"
CYAN = "#00b2f0"
TEXT_SECONDARY = "#9fc3d6"
TEXT_MUTED = "#5f8598"
YELLOW = "#ffd400"
HORIZON_TARGET = {"incremental": 50, "adyacente": 30, "disruptivo": 20}
FACILITADOR_PIN = "IDEAR"

ASSETS_DIR = Path(__file__).parent / "assets"


# ============================================================
# ESTADO COMPARTIDO (en memoria, vivo mientras la app corre)
# ============================================================
@st.cache_resource
def get_shared_state():
    return {
        "lock": threading.Lock(),
        "iniciativas": [],  # [{id, name, type}]
        "horizon_mix": {"incremental": 0, "adyacente": 0, "disruptivo": 0},
        "active_index": -1,
        "decisions": {},  # ini_id -> decision_id
        "votes": {},  # f"{ini_id}__{vp_id}" -> {"i1","i2","i3","i4"}
        "session_id": None,
    }


state = get_shared_state()


def compute_agg(votes):
    """Misma fórmula que la versión Claude: pesos 30/20/30/20, escala 1-5 -> 0-100."""
    if not votes:
        return {"I": None, "B": None, "C": None, "V": None, "puntaje": None, "x": None, "y": None, "cuadrante": None, "n": 0}
    I = sum(v["i1"] for v in votes) / len(votes)
    B = sum(v["i2"] for v in votes) / len(votes)
    C = sum(v["i3"] for v in votes) / len(votes)
    V = sum(v["i4"] for v in votes) / len(votes)
    puntaje_1_5 = 0.30 * I + 0.20 * B + 0.30 * C + 0.20 * V
    puntaje = round(25 * (puntaje_1_5 - 1))
    x_1_5 = (30 * I + 20 * B + 30 * C) / 80
    x = round(25 * (x_1_5 - 1))
    y = round(25 * (V - 1))
    if x >= 50 and y >= 50:
        cuadrante = "avanza"
    elif x < 50 and y >= 50:
        cuadrante = "banco"
    elif x >= 50 and y < 50:
        cuadrante = "resolver"
    else:
        cuadrante = "no_prioriza"
    return {"I": I, "B": B, "C": C, "V": V, "puntaje": puntaje, "x": x, "y": y, "cuadrante": cuadrante, "n": len(votes)}


def vp_score(v):
    """Puntaje individual (0-100) de un solo VP, misma fórmula que el agregado."""
    return round(25 * ((0.30 * v["i1"] + 0.20 * v["i2"] + 0.30 * v["i3"] + 0.20 * v["i4"]) - 1))


def vp_name(vp_id):
    return next((v["name"] for v in VPS if v["id"] == vp_id), vp_id)


_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es():
    """Fecha de hoy en español, sin depender del locale del servidor
    (Streamlit Cloud corre en inglés por defecto — time.strftime('%B') daba
    'September' en vez de 'septiembre')."""
    t = time.localtime()
    return f"{t.tm_mday} de {_MESES_ES[t.tm_mon - 1]} de {t.tm_year}"


# ============================================================
# ESTILO — marca Postobón (navy/cian/Montserrat)
# ============================================================
def inject_css():
    # Cada botón de decisión (Priorizar/Resolver/Banco/No priorizar) debe
    # verse con SU propio color, igual que en la versión Claude — Streamlit
    # pone la key del botón como clase "st-key-<key>" en un contenedor
    # ancestro, así que apuntamos por ahí en vez de por el texto del botón.
    decision_css = "\n".join(
        f'''
        div[class*="_{d["id"]}"] div[data-testid="stButton"] > button {{
            color: {d["color"]} !important;
        }}
        div[class*="_{d["id"]}"] div[data-testid="stButton"] > button[kind="primary"] {{
            background-color: {d["color"]}22 !important;
            border: 1.5px solid {d["color"]} !important;
        }}
        '''
        for d in DECISIONES
    )
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap');
        html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]) {{
            font-family: 'Montserrat', sans-serif !important;
        }}
        .stApp {{ background-color: {NAVY_900}; color: #f7fcff; }}
        h1, h2, h3, h4, h5 {{ color: #f7fcff !important; }}
        div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {{
            background-color: {CYAN}; color: {NAVY_900}; font-weight: 800;
            border-radius: 10px; border: none;
        }}
        div[data-testid="stButton"] > button[kind="secondary"],
        div[data-testid="stDownloadButton"] > button[kind="secondary"] {{
            background-color: rgba(4,32,46,0.28) !important; color: #f7fcff; font-weight: 700;
            border: 1.5px solid rgba(255,255,255,0.35); border-radius: 14px;
            text-align: left; justify-content: flex-start; padding: 13px 16px; transition: border-color .15s;
        }}
        div[data-testid="stButton"] > button[kind="secondary"]:hover,
        div[data-testid="stDownloadButton"] > button[kind="secondary"]:hover {{
            border-color: {CYAN}; color: #f7fcff;
        }}
        .stCaption, .stCaption p {{
            color: {TEXT_SECONDARY} !important; font-size: 12px !important; font-weight: 600 !important;
        }}
        div[data-testid="stForm"], .card {{
            background-color: {NAVY_CARD}; border-radius: 22px; padding: 1.5rem;
            border: 1px solid rgba(255,255,255,0.15);
        }}

        /* Encabezados de sección (los "####") en el estilo "smallhead" original:
           chicos, en mayúscula, con letra espaciada y color secundario — no
           como un título normal. Deja el "##" del título grande sin tocar. */
        h4 {{
            font-size: 12.5px !important; font-weight: 800 !important;
            color: {TEXT_SECONDARY} !important; letter-spacing: 0.06em !important;
            text-transform: uppercase !important; border-bottom: 1px solid rgba(255,255,255,0.12);
            padding-bottom: 10px; margin-bottom: 4px !important;
        }}

        /* "Cambiar rol": un link subrayado discreto, no un botón */
        .st-key-changerole button {{
            background: none !important; border: none !important; box-shadow: none !important;
            color: {TEXT_MUTED} !important; font-size: 11px !important; font-weight: 400 !important;
            text-decoration: underline !important; padding: 0 !important; height: auto !important;
        }}

        /* Etiquetas de los campos (antes se veían gris oscuro casi invisibles) */
        [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label {{
            color: {TEXT_SECONDARY} !important; font-weight: 700 !important;
        }}
        /* Cajas de texto / número / desplegable (antes quedaban blancas por defecto).
           Streamlit cambió de "data-baseweb" a testids tipo "stXxxRootElement" —
           cubrimos ambos esquemas (viejo y nuevo) para que sobreviva futuras
           actualizaciones de Streamlit. */
        div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"],
        div[data-testid$="RootElement"], div[data-testid="stSelectbox"] > div > div,
        div[data-testid="stNumberInput"] > div > div {{
            background-color: rgba(255,255,255,0.06) !important;
            border: 1.5px solid rgba(255,255,255,0.24) !important;
            border-radius: 10px !important;
        }}
        div[data-baseweb="input"] input, div[data-baseweb="select"] div, div[data-baseweb="textarea"] textarea,
        div[data-testid$="RootElement"] input, div[data-testid$="RootElement"] *,
        div[data-testid="stSelectbox"] *, div[data-testid="stNumberInput"] * {{
            color: #f7fcff !important;
        }}
        div[data-testid$="RootElement"] button {{ background-color: transparent !important; }}
        input::placeholder, textarea::placeholder {{ color: {TEXT_SECONDARY} !important; opacity: .8; }}
        ul[data-testid="stSelectboxVirtualDropdown"], div[role="listbox"] {{ background-color: {NAVY_CARD} !important; }}
        ul[data-testid="stSelectboxVirtualDropdown"] li, div[role="listbox"] * {{ color: #f7fcff !important; }}
        /* Cajas de alerta (st.info) con la marca en vez del azul por defecto */
        div[data-testid="stAlertContainer"] {{
            background-color: {NAVY_CARD} !important; border: 1px solid rgba(255,255,255,0.15) !important;
        }}
        div[data-testid="stAlertContainer"] p {{ color: #f7fcff !important; }}

        /* Asegura que el contenido de la app quede SIEMPRE encima de las burbujas de fondo */
        div[data-testid="stAppViewContainer"] {{ position: relative; z-index: 1; }}
        @media (prefers-reduced-motion: reduce) {{ .fizz b {{ animation-duration: .001ms !important; }} }}
        .fizz {{ position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 0; }}
        .fizz b {{
            position: absolute; bottom: -8vh; border-radius: 50%;
            background: radial-gradient(circle at 40% 35%, rgba(255,255,255,.55), rgba(0,178,240,.22) 45%, transparent 72%);
            border: none; box-shadow: 0 0 14px rgba(0,178,240,.25); animation: rise linear infinite; opacity: 0;
        }}
        @keyframes rise {{
            0% {{ transform: translateY(0) scale(.6); opacity: 0; }}
            12% {{ opacity: .6; }}
            90% {{ opacity: .4; }}
            100% {{ transform: translateY(-116vh) scale(1); opacity: 0; }}
        }}
        {decision_css}

        /* ===== Tarjeta de calificación del VP (estilo Kahoot) ===== */
        .st-key-vpcard {{
            background: linear-gradient(135deg, {NAVY_900} 0%, #0c6fae 52%, {CYAN} 100%) !important;
            border-radius: 32px !important; padding: 1.4rem 1.5rem 1.7rem !important;
            max-width: 380px; margin: 0 auto 1.25rem; box-shadow: 0 30px 70px rgba(0,0,0,0.45);
        }}
        .vpnotch {{ width: 70px; height: 5px; background: rgba(255,255,255,0.18); border-radius: 100px; margin: 0 auto 1.1rem; }}
        div[class*="st-key-back_"] button {{
            width: 28px !important; height: 28px !important; min-height: 28px !important;
            border-radius: 50% !important; padding: 0 !important;
            border: 1.5px solid rgba(255,255,255,0.35) !important;
            background: rgba(4,32,46,0.28) !important; color: #fff !important; font-size: 14px !important;
        }}
        .vpprogress {{ display: flex; gap: 6px; margin-top: 7px; }}
        .vpprogress i {{ flex: 1; height: 4px; border-radius: 100px; background: rgba(255,255,255,0.14); display: block; }}
        .vpprogress i.done {{ background: {CYAN}; }}
        .vpprogress i.active {{ background: {CYAN}; opacity: 0.5; }}
        .vpbadge {{
            display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: 0.05em;
            text-transform: uppercase; background: rgba(255,255,255,0.1); color: {TEXT_SECONDARY};
            padding: 4px 10px; border-radius: 6px; margin: 14px 0 10px;
        }}
        .vpqnum {{ font-size: 13px; font-weight: 800; color: var(--accent); letter-spacing: 0.06em; margin: 0 0 6px; }}
        .vpqname {{ font-size: 23px; font-weight: 900; text-transform: uppercase; line-height: 1.18; margin: 0 0 10px; color: #fff !important; }}
        .vpqtext {{ font-size: 14px; color: {TEXT_SECONDARY}; line-height: 1.55; margin: 0 0 1.2rem; }}
        .st-key-optlist div[data-testid="stButton"] > button {{
            position: relative !important; text-align: left !important; padding-left: 50px !important;
            display: flex !important; align-items: center !important; min-height: 48px !important;
        }}
        .st-key-optlist div[data-testid="stButton"] > button::before {{
            position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
            width: 26px; height: 26px; border-radius: 50%;
            border: 1.5px solid rgba(255,255,255,0.45);
            display: flex; align-items: center; justify-content: center;
            font-size: 13px; font-weight: 800; color: #fff;
        }}
        .st-key-optlist > div:nth-child(1) button::before {{ content: "1"; }}
        .st-key-optlist > div:nth-child(2) button::before {{ content: "2"; }}
        .st-key-optlist > div:nth-child(3) button::before {{ content: "3"; }}
        .st-key-optlist > div:nth-child(4) button::before {{ content: "4"; }}
        .st-key-optlist > div:nth-child(5) button::before {{ content: "5"; }}
        .st-key-optlist > div:nth-child(2) button, .st-key-optlist > div:nth-child(4) button {{
            font-style: italic !important; font-weight: 500 !important; color: {TEXT_SECONDARY} !important;
        }}

        /* ===== Mix de horizonte: barra con marca de meta ===== */
        .hmix {{ display: flex; flex-direction: column; gap: 12px; max-width: 620px; margin: 0 auto; }}
        .hmix .label-row {{
            display: flex; justify-content: space-between; font-size: 13px;
            color: {TEXT_SECONDARY}; margin-bottom: 5px; font-weight: 600;
        }}
        .hmix .label-row b {{ color: #f7fcff; font-weight: 800; }}
        .hmix-track {{ position: relative; height: 14px; margin-top: 18px; background: rgba(255,255,255,0.22); border-radius: 7px; }}
        .hmix-fill {{ position: absolute; height: 14px; background: {CYAN}; border-radius: 7px; }}
        .hmix-target {{ position: absolute; top: -4px; width: 2px; height: 22px; background: {YELLOW}; }}
        .hmix-target-label {{
            position: absolute; top: -18px; font-size: 10px; font-weight: 700; color: {YELLOW};
            transform: translateX(-50%); white-space: nowrap;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_bubbles():
    """Burbujas de fondo animadas (tomadas de Calendario_Semana_35.html, con el
    cian de nuestra marca). Puramente decorativo — position:fixed detrás de todo."""
    bubbles_html = "".join(
        f'<b style="left:{(i*61)%100}%;width:{6+((i*37)%34)}px;height:{6+((i*37)%34)}px;'
        f'animation-duration:{8+((i*53)%12)}s;animation-delay:{-((i*29)%12)}s"></b>'
        for i in range(16)
    )
    st.markdown(f'<div class="fizz" aria-hidden="true">{bubbles_html}</div>', unsafe_allow_html=True)


def get_logo_b64():
    logo_path = ASSETS_DIR / "logo_postobon.png"
    if logo_path.exists():
        return base64.b64encode(logo_path.read_bytes()).decode()
    return None


def render_topbar():
    logo_b64 = get_logo_b64()
    if logo_b64:
        # position:fixed (no las columnas de Streamlit, que se apilan en
        # pantallas angostas) para que el logo quede siempre arriba a la
        # derecha, sin importar el ancho de pantalla del VP.
        st.markdown(
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="position:fixed;top:60px;right:24px;height:28px;z-index:999999;">',
            unsafe_allow_html=True,
        )
    st.markdown("## COMITÉ DE INNOVACIÓN")
    st.caption(fecha_es())
    if st.session_state.get("role"):
        if st.button("Cambiar rol", key="changerole", type="secondary"):
            st.session_state.role = None
            st.rerun()
    st.divider()


# ============================================================
# RESOLUCIÓN DE ROL — por link personalizado (?vp=<id> o ?role=facilitador)
# o por selector manual (con fallback si no llega el parámetro)
# ============================================================
def resolve_role():
    if "role" not in st.session_state:
        st.session_state.role = None
    if st.session_state.role is None:
        # El rol de facilitador SIEMPRE requiere la clave (ver render_role_picker),
        # incluso si llega por ?role=facilitador en la URL — por eso ese caso no
        # se resuelve aquí de forma automática.
        vp_param = st.query_params.get("vp")
        if vp_param and any(v["id"] == vp_param for v in VPS):
            st.session_state.role = vp_param


def render_role_picker():
    st.markdown("#### Selecciona tu rol")
    for v in VPS:
        if st.button(v["name"], key=f"role_{v['id']}", use_container_width=True):
            st.session_state.role = v["id"]
            st.rerun()

    st.write("")
    with st.container(border=True):
        st.markdown("**Soy el facilitador (pantalla del Comité)**")
        pin = st.text_input("Clave del facilitador", type="password", key="facpin", label_visibility="collapsed", placeholder="Clave del facilitador")
        if st.button("Entrar", key="facpin_btn", use_container_width=True, type="primary"):
            if pin == FACILITADOR_PIN:
                st.session_state.role = "facilitador"
                st.rerun()
            else:
                st.error("Clave incorrecta, intenta de nuevo.")


# ============================================================
# VISTA VP — estilo Kahoot, una pregunta a la vez
# ============================================================
def render_vp_view(vp_id):
    with state["lock"]:
        iniciativas = list(state["iniciativas"])
        active_index = state["active_index"]

    if active_index == -1 or not iniciativas:
        st.info("Esperando que inicie la sesión. Esta pantalla se actualiza sola.")
        return
    if active_index >= len(iniciativas):
        st.success("✓ Sesión terminada. Gracias por participar. Los resultados se revisan en la pantalla del Comité.")
        return

    ini = iniciativas[active_index]
    vote_key = f"{ini['id']}__{vp_id}"
    with state["lock"]:
        already = vote_key in state["votes"]
    if already:
        st.success("✓ Calificación registrada. Los resultados quedan ocultos hasta que termine el último pitch.")
        return

    step_key = f"step__{vp_id}"
    sel_key = f"sel__{vp_id}__{ini['id']}"
    current_ini_key = f"current_ini__{vp_id}"
    if st.session_state.get(current_ini_key) != ini["id"]:
        st.session_state[step_key] = 0
        st.session_state[current_ini_key] = ini["id"]
        st.session_state[sel_key] = {}
    if sel_key not in st.session_state:
        st.session_state[sel_key] = {}

    idx = st.session_state[step_key]
    c = CRITERIA[idx]
    sel = st.session_state[sel_key]

    with st.container(key="vpcard"):
        st.markdown('<div class="vpnotch"></div>', unsafe_allow_html=True)

        hcol1, hcol2 = st.columns([1, 5])
        with hcol1:
            back_clicked = st.button("←", key=f"back_{vp_id}", disabled=(idx == 0))
        with hcol2:
            dots = "".join(
                f'<i class="{"done" if i < idx else ("active" if i == idx else "")}"></i>'
                for i in range(len(CRITERIA))
            )
            st.markdown(f'<div class="vpprogress">{dots}</div>', unsafe_allow_html=True)

        st.markdown(
            f'<span class="vpbadge">{html.escape(ini["type"])} · {html.escape(ini["name"])}</span>'
            f'<p class="vpqnum" style="--accent:{c["accent"]}">Pregunta {idx+1} de {len(CRITERIA)}</p>'
            f'<p class="vpqname">{html.escape(c["name"])}</p>'
            f'<p class="vpqtext">{html.escape(c["q"])}</p>',
            unsafe_allow_html=True,
        )

        with st.container(key="optlist"):
            for n in range(1, 6):
                raw = c["opts"][n - 1]
                label = raw if raw else "Posición intermedia"
                if st.button(label, key=f"opt_{vp_id}_{ini['id']}_{idx}_{n}", use_container_width=True):
                    sel[idx] = n
                    if idx < len(CRITERIA) - 1:
                        st.session_state[step_key] = idx + 1
                    else:
                        with state["lock"]:
                            state["votes"][vote_key] = {"i1": sel[0], "i2": sel[1], "i3": sel[2], "i4": sel[3]}
                    st.rerun()

    if back_clicked and idx > 0:
        st.session_state[step_key] = idx - 1
        st.rerun()


# ============================================================
# VISTA FACILITADOR — preparar sesión
# ============================================================
def render_facilitator_setup():
    st.markdown("#### Preparar sesión — agregar iniciativas")
    with st.form("add_ini_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Nombre de la iniciativa", placeholder="Ej. Punto único de venta")
        tipo = c2.selectbox("Tipo", TIPOS)
        c3.write("")
        c3.write("")
        submitted = c3.form_submit_button("Agregar", use_container_width=True)
    if submitted and name.strip():
        with state["lock"]:
            state["iniciativas"].append({"id": f"ini{int(time.time()*1000)}", "name": name.strip(), "type": tipo})
        st.rerun()

    with state["lock"]:
        iniciativas = list(state["iniciativas"])

    if not iniciativas:
        st.caption("Aún no hay iniciativas agregadas.")
    else:
        for i, ini in enumerate(iniciativas):
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.write(f"**{i+1}. {ini['name']}**")
            c2.write(ini["type"])
            if c3.button("✕", key=f"rm_{ini['id']}"):
                with state["lock"]:
                    state["iniciativas"] = [x for x in state["iniciativas"] if x["id"] != ini["id"]]
                st.rerun()

    st.markdown("#### Mix de horizonte actual del portafolio (%)")
    st.caption("Escribe el dato real del portafolio completo (no de las iniciativas de hoy) — la meta fija 50/30/20 se muestra en el reveal.")
    with state["lock"]:
        hm = dict(state["horizon_mix"])
    c1, c2, c3 = st.columns(3)
    inc = c1.number_input("Incremental", min_value=0, max_value=100, value=hm["incremental"], key="hmix_inc")
    ady = c2.number_input("Adyacente", min_value=0, max_value=100, value=hm["adyacente"], key="hmix_ady")
    dis = c3.number_input("Disruptivo", min_value=0, max_value=100, value=hm["disruptivo"], key="hmix_dis")

    if st.button("Iniciar sesión", disabled=len(iniciativas) == 0, use_container_width=True, type="primary"):
        with state["lock"]:
            state["horizon_mix"] = {"incremental": inc, "adyacente": ady, "disruptivo": dis}
            state["active_index"] = 0
            if not state.get("session_id"):
                state["session_id"] = time.strftime("%Y-%m-%d %H:%M")
        st.rerun()

    st.caption(
        "Comparte con el Comité este mismo enlace. Para dar a cada VP su enlace personalizado, "
        "agrega `?vp=<id>` a la URL (ver lista de ids en el código) — evita que tengan que elegir su rol a mano."
    )


def render_facilitator_control():
    with state["lock"]:
        iniciativas = list(state["iniciativas"])
        active_index = state["active_index"]
        votes = dict(state["votes"])

    ini = iniciativas[active_index]
    count = sum(1 for k in votes if k.startswith(ini["id"] + "__"))
    is_last = active_index == len(iniciativas) - 1

    st.markdown(f"###### Iniciativa {active_index+1} de {len(iniciativas)}")
    st.markdown(f"## {ini['name']}")
    st.write(ini["type"])
    st.info(f"{count} de {len(VPS)} VPs han respondido")

    c1, c2 = st.columns(2)
    if c1.button("← Iniciativa anterior", disabled=active_index == 0, use_container_width=True):
        with state["lock"]:
            state["active_index"] -= 1
        st.rerun()
    if c2.button("Ver reveal" if is_last else "Siguiente iniciativa →", use_container_width=True, type="primary"):
        with state["lock"]:
            state["active_index"] += 1
        st.rerun()


def render_facilitator_reveal():
    with state["lock"]:
        iniciativas = list(state["iniciativas"])
        votes = dict(state["votes"])
        decisions = dict(state["decisions"])
        hmix = dict(state["horizon_mix"])
        session_id = state.get("session_id")

    fecha = fecha_es()

    aggs = []
    for ini in iniciativas:
        ini_votes = [v for k, v in votes.items() if k.startswith(ini["id"] + "__")]
        aggs.append({"ini": ini, **compute_agg(ini_votes)})

    st.markdown(f"<p style='text-align:center;color:{CYAN};font-weight:800;letter-spacing:0.08em;'>DECISION ROUND</p>", unsafe_allow_html=True)
    fig, ax = plt.subplots(figsize=(5.5, 4))
    fig.patch.set_facecolor(NAVY_CARD)
    ax.set_facecolor("#ffffff")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axvline(50, color="#d9dee2", linestyle="-", linewidth=2)
    ax.axhline(50, color="#d9dee2", linestyle="-", linewidth=2)
    ax.text(75, 96, "Priorizar", ha="center", fontweight="bold", color="#2CB1AE", fontsize=12)
    ax.text(25, 96, "Banco de iniciativas", ha="center", fontweight="bold", color="#3182D3", fontsize=12)
    ax.text(75, 3, "Resolver barreras", ha="center", fontweight="bold", color="#FFD347", fontsize=12)
    ax.text(25, 3, "No priorizar", ha="center", fontweight="bold", color="#FF4382", fontsize=12)
    ax.set_xlabel("ATRACTIVO", color=TEXT_SECONDARY, fontweight="bold")
    ax.set_ylabel("VIABILIDAD", color=TEXT_SECONDARY, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#b3bec5")
    for i, a in enumerate(aggs):
        if a["x"] is None:
            continue
        meta = QUAD_META[a["cuadrante"]]
        ax.scatter([a["x"]], [a["y"]], s=420, color=meta["text"], zorder=5, edgecolors="none")
        ax.text(a["x"], a["y"], str(i + 1), ha="center", va="center", color="white", fontweight="bold", zorder=6, fontsize=9)
    st.pyplot(fig, use_container_width=True)

    st.markdown(f"**{len(iniciativas)}** iniciativas evaluadas")

    st.markdown("#### Puntuación de las iniciativas")
    for i, a in enumerate(aggs):
        meta = QUAD_META[a["cuadrante"]] if a["cuadrante"] else {"label": "Sin votos", "text": "#7fa4b8"}
        c1, c2, c3, c4 = st.columns([0.5, 3, 1, 2])
        c1.markdown(f"**{i+1}**")
        c2.markdown(f"**{a['ini']['name']}**  \n<span style='color:{TEXT_SECONDARY};font-size:0.85em;'>{a['ini']['type']}</span>", unsafe_allow_html=True)
        c3.markdown(f"### {a['puntaje'] if a['puntaje'] is not None else '—'}")
        c4.markdown(
            f"<span style='background:{meta['text']}22;color:{meta['text']};padding:4px 10px;"
            f"border-radius:100px;font-weight:700;font-size:0.8em;'>{meta['label'].upper()}</span>",
            unsafe_allow_html=True,
        )
        dcols = st.columns(4)
        for d, dc in zip(DECISIONES, dcols):
            selected = decisions.get(a["ini"]["id"]) == d["id"]
            if dc.button(d["label"], key=f"dec_{a['ini']['id']}_{d['id']}", use_container_width=True,
                         type="primary" if selected else "secondary"):
                with state["lock"]:
                    state["decisions"][a["ini"]["id"]] = d["id"]
                st.rerun()
        st.write("")

    st.markdown("#### Mix de horizonte vs. meta 50/30/20")
    hmix_rows = ""
    for label, key in [("Incremental", "incremental"), ("Adyacente", "adyacente"), ("Disruptivo", "disruptivo")]:
        target = HORIZON_TARGET[key]
        real = min(max(hmix[key], 0), 100)
        hmix_rows += (
            f'<div class="hmix-row"><div class="label-row"><span>{label}</span><b>{hmix[key]}%</b></div>'
            f'<div class="hmix-track"><div class="hmix-fill" style="width:{real}%;"></div>'
            f'<div class="hmix-target" style="left:{target}%;"></div>'
            f'<span class="hmix-target-label" style="left:{target}%;">{target}%</span>'
            f'</div></div>'
        )
    st.markdown(f'<div class="hmix">{hmix_rows}</div>', unsafe_allow_html=True)
    st.caption("Línea amarilla = meta corporativa. El dato real lo escribe el facilitador al preparar la sesión.")

    st.divider()

    # ---- Hoja "Resumen por iniciativa" ----
    resumen_rows = []
    for i, a in enumerate(aggs):
        dec_id = decisions.get(a["ini"]["id"])
        dec_label = next((d["label"] for d in DECISIONES if d["id"] == dec_id), None) or "Sin decisión registrada"
        quad_label = QUAD_META[a["cuadrante"]]["label"] if a["cuadrante"] else "Sin votos"
        resumen_rows.append({
            "Fecha": fecha,
            "Sesión": session_id or fecha,
            "#": i + 1,
            "Iniciativa": a["ini"]["name"],
            "Tipo": a["ini"]["type"],
            "Votantes": a["n"],
            "Promedio Impacto": round(a["I"], 2) if a["I"] is not None else "—",
            "Promedio Beneficio-recursos": round(a["B"], 2) if a["B"] is not None else "—",
            "Promedio Contribución": round(a["C"], 2) if a["C"] is not None else "—",
            "Promedio Viabilidad": round(a["V"], 2) if a["V"] is not None else "—",
            "Coordenada X (Atractivo)": a["x"] if a["x"] is not None else "—",
            "Coordenada Y (Viabilidad)": a["y"] if a["y"] is not None else "—",
            "Puntaje": a["puntaje"] if a["puntaje"] is not None else "—",
            "Cuadrante calculado": quad_label,
            "Decisión final": dec_label,
        })
    df_resumen = pd.DataFrame(resumen_rows)

    # ---- Hoja "Detalle por VP" (para calibrar el modelo) ----
    detalle_rows = []
    for i, a in enumerate(aggs):
        ini_id = a["ini"]["id"]
        for k, v in votes.items():
            if k.split("__")[0] != ini_id:
                continue
            this_vp_id = k.split("__")[1]
            detalle_rows.append({
                "Fecha": fecha,
                "Sesión": session_id or fecha,
                "#": i + 1,
                "Iniciativa": a["ini"]["name"],
                "Tipo": a["ini"]["type"],
                "VP": vp_name(this_vp_id),
                "Impacto potencial (1-5)": v["i1"],
                "Beneficio-recursos (1-5)": v["i2"],
                "Contribución estratégica (1-5)": v["i3"],
                "Viabilidad (1-5)": v["i4"],
                "Puntaje del VP (0-100)": vp_score(v),
            })
    df_detalle = pd.DataFrame(detalle_rows)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_resumen.to_excel(writer, index=False, sheet_name="Resumen por iniciativa")
        df_detalle.to_excel(writer, index=False, sheet_name="Detalle por VP")
    st.download_button(
        "Descargar Excel",
        data=buf.getvalue(),
        file_name="Shark Tank G1 - resumen.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.write("")
    confirmado = st.checkbox("Ya descargué el Excel con los resultados de esta sesión", key="confirm_reset")
    if st.button("Terminar y preparar nueva sesión", use_container_width=True, disabled=not confirmado):
        with state["lock"]:
            ini_ids = {i["id"] for i in state["iniciativas"]}
            state["votes"] = {k: v for k, v in state["votes"].items() if k.split("__")[0] not in ini_ids}
            state["iniciativas"] = []
            state["active_index"] = -1
            state["decisions"] = {}
            state["session_id"] = None
        st.rerun()
    if not confirmado:
        st.caption("Marca la casilla de arriba para habilitar este botón — evita borrar la sesión sin haber guardado el Excel.")


# ============================================================
# MAIN
# ============================================================
def main():
    inject_css()
    render_bubbles()
    resolve_role()
    render_topbar()

    role = st.session_state.get("role")
    if role == "facilitador":
        with state["lock"]:
            active_index = state["active_index"]
            n = len(state["iniciativas"])
        if active_index == -1:
            render_facilitator_setup()
        elif active_index < n:
            render_facilitator_control()
        else:
            render_facilitator_reveal()
    elif role and any(v["id"] == role for v in VPS):
        render_vp_view(role)
    else:
        render_role_picker()

    # 2s era demasiado agresivo para el plan gratuito de Streamlit Cloud —
    # saturaba la conexión y causaba desconexiones/reconexiones visibles
    # (la app se veía "sin estilo" por un instante). 5s sigue sintiéndose
    # casi en vivo con mucha menos carga.
    st_autorefresh(interval=5000, key="autorefresh")


if __name__ == "__main__":
    main()
