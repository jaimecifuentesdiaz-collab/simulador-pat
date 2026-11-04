"""Pestaña Escenario: rubro, proyecto, versiones guardadas y el escenario base de cada rubro (Agrozzi, pellet, chip y leña)."""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.escenarios.biomasa_comun import resumen_corto
from pat_sim.datos.bd import NOMBRE_AGROZZI
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

ESCENARIOS_BIOMASA = {"pellet": pellet, "chip": chip, "lena": lena}
DESCRIPCION = {
    "pellet": "Aserrín verde de pino radiata: secador rotatorio, molino, pelletizadora, enfriador, criba y ensacado (ENplus A1). "
              "El generador quema astilla con corteza para el aire del secador.",
    "chip": "Rollizos verdes de pino radiata: astilladora, criba, secador de banda a baja temperatura y acopio (ISO 17225-4, clase M25).",
    "lena": "Trozas de eucalipto: procesadora (sierra y partidora), secador de leña y acopio con el límite de leña seca (25 % en base seca).",
}

PARAMS_AGROZZI = [  # (argumento de model.py, etiqueta, mínimo, máximo, paso, formato)
    ("season", "Tomate procesado por temporada (t)", 100000.0, 900000.0, 10000.0, "%.0f"),
    ("days", "Días de operación de la temporada", 30, 150, 1, "%d"),
    ("Thb", "Temperatura de salida del hot break (°C)", 75.0, 96.0, 1.0, "%.1f"),
    ("xP", "Sólidos solubles de la pasta (°Brix/100)", 0.28, 0.36, 0.01, "%.2f"),
    ("N", "Efectos del evaporador Venus", 2, 5, 1, "%d"),
    ("TcMVR", "Temperatura de condensación de los MVR (°C)", 70.0, 85.0, 1.0, "%.1f"),
    ("etaMVR", "Rendimiento isentrópico de los compresores MVR", 0.6, 0.9, 0.01, "%.2f"),
    ("dT", "Aproximación mínima de temperatura (°C)", 2.0, 15.0, 0.5, "%.1f"),
    ("Tfin", "Temperatura final de los residuales (°C)", 20.0, 40.0, 1.0, "%.1f"),
]


def _limpiar_claves():
    """Al cambiar de planta, los deslizadores de Recuperación de calor y el rubro toman los valores de la planta nueva."""
    for k in ("rc_dT", "rc_Tfin", "esc_rubro"):
        st.session_state.pop(k, None)


def _cambiar_rubro():
    """PAT 132: al elegir otro rubro se carga de inmediato su escenario base, así Diseño, Operación, Calidad SPC y las demás
    pestañas muestran ese mismo rubro sin volver a elegirlo. «Equipos generales» no tiene escenario: deja la planta como está."""
    ss = st.session_state; r = ss.get("esc_rubro"); pl = C.planta()
    if r == pl.rubro or (r not in ESCENARIOS_BIOMASA and r != "tomate"):
        return
    bd = C.obtener_bd()
    mod = ESCENARIOS_BIOMASA.get(r)
    try:
        ss.pl = mod.crear() if mod else agrozzi.crear()
        nombre = mod.NOMBRE if mod else NOMBRE_AGROZZI
        ss.pid = (bd.obtener_proyecto(nombre) or {}).get("id"); ss.vid = None
        for k in ("rc_dT", "rc_Tfin"):
            ss.pop(k, None)
        ss.aviso_rubro = ("ok", f"Cargado el escenario base del rubro {RUBROS[r]}: {ss.pl.nombre}. Las demás pestañas ya trabajan con él.")
    except Exception as e:
        ss.aviso_rubro = ("error", f"No se pudo cargar el escenario base de {RUBROS.get(r, r)}: {e}")


def mostrar():
    ss = st.session_state; bd = C.obtener_bd(); pl = C.planta()
    st.subheader("Escenario")
    c1, c2 = st.columns([1, 2])
    with c1:
        rubros = list(RUBROS.items())
        idx = [k for k, _ in rubros].index(pl.rubro) if pl.rubro in RUBROS else 0
        if ss.get("esc_rubro") not in (None, "general") and ss.get("esc_rubro") != pl.rubro:
            ss.pop("esc_rubro")                     # la planta cambió por otra vía (versión cargada): el selector la sigue
        sel = st.selectbox("Rubro", [k for k, _ in rubros], index=idx, format_func=lambda k: RUBROS[k], key="esc_rubro",
                           on_change=_cambiar_rubro,
                           help="Al cambiar el rubro se carga su escenario base y lo usan todas las pestañas. Guarde antes una versión si modificó la planta.")
        if sel in DESCRIPCION:
            C.ayuda(DESCRIPCION[sel])   # PAT 134: ayuda «?»
        av = ss.pop("aviso_rubro", None)
        if av:
            (st.success if av[0] == "ok" else st.error)(av[1])
    with c2:
        st.markdown(f"**Planta actual:** {pl.nombre}  \n**Equipos:** {len(pl.equipos)} · **Conexiones:** {len(pl.conexiones)} · "
                    f"**Lazos de instrumentación:** {len(pl.instrumentos)}")
        C.ayuda("Las cifras de la planta basada en Agrozzi reproducen el Modelo_PAT_Agrozzi_v2.xlsx (Capítulo 1). "   # PAT 134
                "No hubo visita a la planta: cada supuesto se justifica con el fabricante (CFT) o la literatura.")

    proy = bd.listar_proyectos()
    AT.tabla("esc_proyectos", "Proyectos guardados", 4)   # PAT 134: «?» de la tabla
    if proy:
        C.mostrar_tabla([dict(nombre=p["nombre"], rubro=RUBROS.get(p["rubro"], p["rubro"]), n=p["n_versiones"], mod=p["modificado"]) for p in proy],
                        [("nombre", "Proyecto", "txt", 0), ("rubro", "Rubro", "txt", 0), ("n", "Versiones", "num", 0), ("mod", "Modificado", "txt", 0)])
    a, b = st.columns(2)
    with a:
        nombres = [p["nombre"] for p in proy]
        actual = next((p["nombre"] for p in proy if p["id"] == ss.get("pid")), nombres[0] if nombres else None)
        elegido = st.selectbox("Proyecto", nombres, index=nombres.index(actual) if actual in nombres else 0) if nombres else None
        vers = bd.listar_versiones(next(p["id"] for p in proy if p["nombre"] == elegido)) if elegido else []
        vsel = st.selectbox("Versión", vers, format_func=lambda v: f"v{v['numero']} · {v['fecha']} · {v['nota'] or 'sin nota'}") if vers else None
        if st.button("Cargar versión", disabled=vsel is None):
            ss.pl = C.con_capacidades(bd.cargar_version(vsel["id"])); ss.pid = vsel["proyecto_id"]; ss.vid = vsel["id"]
            st.success(f"Cargada la versión {vsel['numero']} de «{elegido}».")
            _limpiar_claves()
            st.rerun()
    with b:
        nuevo = st.text_input("Nuevo proyecto (se guarda con la planta actual)", placeholder="Nombre del proyecto")
        desc = st.text_input("Descripción", "")
        if st.button("Crear proyecto", disabled=not nuevo.strip()):
            try:
                pid = bd.crear_proyecto(nuevo, pl.rubro, desc)
                v = bd.guardar_version(pid, pl, "Versión inicial")
                ss.pid, ss.vid = pid, v["id"]
                st.success(f"Proyecto «{nuevo}» creado con la versión 1.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    from . import s_proyecto                       # PAT 134: proyecto, versión y coma decimal (antes en la barra lateral)
    s_proyecto.mostrar()
    from . import s_plantillas, s_datos_planta     # PAT 133, mejoras 14 y 19
    s_plantillas.mostrar()
    s_datos_planta.mostrar()
    if sel in ESCENARIOS_BIOMASA:
        _bloque_biomasa(sel, ESCENARIOS_BIOMASA[sel], bd, pl)
        return

    C.ayuda("Recrea la línea de pasta de tomate con los parámetros de partida (los de model.py). "   # PAT 134
            "Reemplaza la planta de la sesión; la base de datos no cambia hasta que guarde una versión.", "Planta basada en Agrozzi")
    base = (pl._p if getattr(pl, "_p", None) and pl.nombre.startswith("Planta basada en Agrozzi") else agrozzi.BASE)
    cols = st.columns(3); kw = {}
    for i, (k, et, lo, hi, paso, f) in enumerate(PARAMS_AGROZZI):
        with cols[i % 3]:
            v0 = base.get(k, agrozzi.BASE[k])
            if isinstance(lo, int):
                kw[k] = st.number_input(et, min_value=lo, max_value=hi, value=int(v0), step=int(paso), key=f"ag_{k}")
            else:
                kw[k] = st.number_input(et, min_value=float(lo), max_value=float(hi), value=float(v0), step=float(paso), format=f, key=f"ag_{k}")
    cols = st.columns(2)
    with cols[0]:
        tvr = st.checkbox("Termocompresor (TVR) en el Venus", value=bool(base.get("tvr", True)), key="ag_tvr")
    with cols[1]:
        flash = st.checkbox("Enfriamiento flash al vacío", value=bool(base.get("flash", True)), key="ag_flash")
    if st.button("Cargar la planta basada en Agrozzi con estos parámetros", type="primary"):
        try:
            ss.pl = agrozzi.crear(tvr=tvr, flash=flash, **kw)
            ss.pid = (bd.obtener_proyecto(NOMBRE_AGROZZI) or {}).get("id"); ss.vid = None
            st.success("Planta recreada y resuelta.")
            _limpiar_claves()
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo crear la planta: {e}")


def _bloque_biomasa(rubro, mod, bd, pl):
    """Escenario base de un rubro de biomasa: parámetros de partida, botón para cargarlo y sus cifras de control."""
    ss = st.session_state
    C.ayuda("Cada equipo trae sus parámetros con fuente (pestaña Diseño). Reemplaza la planta de la sesión; "   # PAT 134
            "la base de datos no cambia hasta que guarde una versión.", mod.NOMBRE)
    base = pl._p if getattr(pl, "_p", None) and pl.nombre == mod.NOMBRE else mod.BASE
    cols = st.columns(3); kw = {}
    for i, (k, et, lo, hi, paso, f) in enumerate(mod.PARAMS):
        with cols[i % 3]:
            v0 = base.get(k, mod.BASE[k])
            if isinstance(lo, int):
                kw[k] = st.number_input(et, min_value=lo, max_value=hi, value=int(v0), step=int(paso), key=f"{rubro}_{k}")
            else:
                kw[k] = st.number_input(et, min_value=float(lo), max_value=float(hi), value=float(v0), step=float(paso), format=f, key=f"{rubro}_{k}")
    if st.button(f"Cargar la {mod.NOMBRE[0].lower() + mod.NOMBRE[1:]} con estos parámetros", type="primary", key=f"cargar_{rubro}"):
        if "Tae" in kw and "Tas" in kw and kw["Tae"] <= kw["Tas"]:
            st.error("La temperatura del aire de secado debe ser mayor que la del escape.")
            return
        try:
            ss.pl = mod.crear(**kw)
            ss.pid = (bd.obtener_proyecto(mod.NOMBRE) or {}).get("id"); ss.vid = None
            st.success("Planta creada y resuelta.")
            _limpiar_claves()
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo crear la planta: {e}")
    if pl.nombre == mod.NOMBRE and pl.resuelta:
        r = resumen_corto(pl)
        st.markdown("#### Cifras de control de la planta actual")
        a, b, c, d = st.columns(4)
        a.metric("Producto", C.fmt(r["producto_t_h"], 2) + " t/h", f"humedad {C.pct(r['humedad_producto'])}", delta_color="off")
        b.metric("Poder calorífico del producto", C.fmt(r["PCI_producto"], 2) + " MJ/kg", "inferior, base húmeda", delta_color="off")
        c.metric("Calor de secado", C.fmt(r["calor_secado_kW"], 0) + " kW", f"{C.fmt(r['consumo_MJ_kg_agua'], 2)} MJ por kg de agua", delta_color="off")
        d.metric("Cascada en serie", C.fmt(r["cascada"], 0) + " kW", C.pct(r["cobertura_cascada"]) + " del calor de secado", delta_color="off")
        if pl.avisos:
            for a_ in pl.avisos:
                st.warning(a_)
