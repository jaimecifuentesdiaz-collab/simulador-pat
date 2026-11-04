"""Sección «Excel de ida y vuelta» de la pestaña Datos de entrada (PAT 134), como las tablas globales y el Excel
Import/Export de FlexSim: descargar la plantilla con las tablas de la planta, subir el libro editado, revisar la
validación, aplicar los cambios (planta, temporada, economía y datos medidos) y descargar los resultados de las corridas.
Motor en pat_sim/motor/libro_planta.py."""
from __future__ import annotations
import hashlib
import streamlit as st
from pat_sim.motor import libro_planta as L
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DESTINOS = {"planta": "Planta", "temporada": "Temporada", "economia": "Economía", "datos_medidos": "Datos medidos"}


def _txt(v) -> str:
    return L._t(v)


def _bytes(arch) -> bytes:
    try:
        return arch.getvalue()
    except AttributeError:
        return arch if isinstance(arch, bytes) else (arch.encode() if isinstance(arch, str) else b"")


def _tabla_cambios(cambios):
    AT.tabla("xl_cambios", "Cambios del Excel")   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(c, dest=DESTINOS.get(c["destino"], c["destino"]), ant=_txt(c["antes"]), des=_txt(c["despues"]),
                          lugar=f"{c['hoja']}, fila {c['fila']}") for c in cambios],
                    [("dest", "Destino", "txt", 0), ("lugar", "Hoja y fila", "txt", 0), ("objeto", "Equipo o tabla", "txt", 0),
                     ("nombre", "Parámetro", "txt", 0), ("ant", "Antes", "cen", 0), ("des", "Después", "cen", 0), ("unidad", "Unidad", "txt", 0),
                     ("nota", "Nota", "txt", 0)])


def _aplicar(pl, v):
    """Aplica la validación: la planta se resuelve con C.resolver() (si no resuelve, se deshace); la temporada, la economía
    y los datos medidos se guardan en la sesión."""
    ss = st.session_state
    det = L.aplicar(pl, v)
    if v.get("planta"):
        if not C.resolver(pl):
            L.deshacer(pl, v)
            C.resolver(pl)
            st.error("La planta no resuelve con los valores del Excel; no se aplicó ningún cambio a la planta.")
            return None
    if v.get("temporada") is not None:
        ss.setdefault("temporada", {})[pl.rubro] = dict(ss.get("temporada", {}).get(pl.rubro) or {}, **v["temporada"])
    if v.get("economia") is not None:
        ss.economia = dict(ss.get("economia") or {}, **v["economia"])
    if v.get("datos_medidos") is not None:
        ss.datos_medidos = dict(ss.get("datos_medidos") or {}, **{k: [float(x) for x in xs] for k, xs in v["datos_medidos"].items()})
    return det


def _resultados(pl):
    ss = st.session_state
    C.ayuda("La temporada se simula con los parámetros de la pestaña Temporada; la recuperación de calor sale del resumen de la planta.",   # PAT 134: ayuda «?»
            "Resultados de las corridas", 5)
    op = C.operacion() if ss.get("op") is not None and getattr(ss.get("op"), "turnos", None) else None
    dist = ss.get("distribuciones")
    n = len(op.turnos) if op is not None else 0
    st.caption(f"Turnos de Operación: {n}. Distribuciones ajustadas: {', '.join(dist) if dist else 'ninguna'}.")
    if not pl.resuelta:
        st.info("Resuelva la planta para exportar los resultados de las corridas.")
        return
    try:
        b = L.resultados_xlsx(pl, op=op, temporada=(ss.get("temporada") or {}).get(pl.rubro), economia=ss.get("economia"),
                              distribuciones=dist, resumen=C.resumen_o_nada())
    except Exception as e:
        st.error(f"No se pudo armar el libro de resultados: {e}")
        return
    st.download_button("Descargar los resultados de las corridas (Excel)", b, file_name=f"Resultados_corridas_{pl.rubro}_PAT134.xlsx",
                       mime=MIME, key="xl_resultados", width="stretch")


def mostrar():
    ss = st.session_state; pl = C.planta()
    C.ayuda("Descargue la plantilla, edite en Excel solo las columnas que indica la hoja Leame (valores de los equipos, capacidades, "   # PAT 134
            "supuestos de temporada, economía y datos medidos) y súbala. Se acepta coma decimal. Nada cambia hasta presionar «Aplicar a la planta».",
            "Excel de ida y vuelta (como las tablas globales de FlexSim)", 5)
    tem = (ss.get("temporada") or {}).get(pl.rubro); eco = ss.get("economia"); dm = ss.get("datos_medidos") or {}
    a, b = st.columns(2)
    try:
        plantilla = L.plantilla_xlsx(pl, temporada=tem, economia=eco, datos_medidos=dm)
        a.download_button("Descargar la plantilla de la planta (Excel)", plantilla, file_name=f"Plantilla_planta_{pl.rubro}_PAT134.xlsx",
                          mime=MIME, key="xl_plantilla", width="stretch")
    except Exception as e:
        a.error(f"No se pudo armar la plantilla: {e}")
    arch = b.file_uploader("Subir el libro editado (.xlsx)", type=["xlsx"], key="xl_archivo")
    if arch is not None:
        datos = _bytes(arch); huella = hashlib.sha1(datos).hexdigest()
        try:
            tablas = L.leer_xlsx(datos)
            v = L.validar(pl, tablas, temporada=tem, economia=eco, datos_medidos=dm)
        except Exception as e:
            st.error(f"No se pudo leer el libro: {e}")
            v = None
        if v is not None:
            g = L.separar(v)
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Cambios a la planta", len(g["planta"]))
            m2.metric("Cambios a temporada", len(g["temporada"]))
            m3.metric("Cambios a economía", len(g["economia"]))
            m4.metric("Series medidas que cambian", len(g["datos_medidos"]))
            m5.metric("Errores", len(v["errores"]))
            for e in v["errores"]:
                st.error(e)
            if v["avisos"]:
                with st.expander(f"Avisos ({len(v['avisos'])})"):
                    for x in v["avisos"]:
                        st.warning(x)
            if v["cambios"]:
                _tabla_cambios(v["cambios"])
                if v["errores"]:
                    st.caption("Las filas con error no se aplican; el resto de los cambios sí.")
                if ss.get("xl_aplicado") == huella:
                    st.success("Este libro ya está aplicado.")
                elif st.button("Aplicar a la planta", type="primary", key="xl_aplicar"):
                    det = _aplicar(pl, v)
                    if det is not None:
                        ss["xl_aplicado"] = huella; ss["xl_detalle"] = det
                        txt = f"Se aplicaron {len(det)} cambios" if len(det) != 1 else "Se aplicó 1 cambio"
                        st.success(txt + (" y la planta se volvió a resolver" if g["planta"] else "") + ". Guarde una versión para conservarlos.")
            else:
                st.info("El libro no trae cambios respecto de la planta y la sesión actuales.")
    det = ss.get("xl_detalle")
    if det:
        with st.expander(f"Último Excel aplicado ({len(det)} cambios)"):
            for x in det:
                st.markdown("- " + C.esc(x))
    if dm:
        st.caption("Datos medidos en la sesión: " + "; ".join(f"{k} ({len(x)} valores)" for k, x in dm.items()))
    _resultados(pl)
