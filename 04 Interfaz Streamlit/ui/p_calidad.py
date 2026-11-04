"""Pestaña Calidad SPC: laboratorio virtual con resultado diferido, acciones correctivas y control estadístico (PAT 130).

Como la pestaña «Calidad SPC» del simulador del profesor (sampleLab, deliverLab, renderLab y drawSPC), adaptada al PAT:
las variables y sus especificaciones están en pat_sim.catalogos.calidad (pasta de tomate: °Brix, temperatura de
esterilización, pH, consistencia Bostwick y recuento de mohos Howard; pellet: ENplus A1 como el profesor; chip y leña:
su norma). Las acciones correctivas son parámetros de la planta, así que también cambian el vapor y la recuperación de calor.
La carta es de individuos con rango móvil (Montgomery, 2020) y suma la regla de ocho puntos seguidos a un lado.
"""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import operacion as OP
from pat_sim.catalogos import calidad as Q
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from .p_operacion import ejecutar_turno, tomar_muestra, avisos


def _estado(v, x) -> str:
    if x is None:
        return "Pendiente"
    return "Conforme" if (v.lo is None or x >= v.lo) and (v.hi is None or x <= v.hi) else "Fuera de especificación"


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Calidad y control estadístico de procesos")
    avisos("cal")
    if not C.exigir_resuelta():
        return
    op = C.operacion(); vs = Q.variables(pl)
    if not vs:
        st.info("Esta planta no tiene variables de calidad definidas: el laboratorio está disponible para la pasta de tomate y para los productos de biomasa.")
        return
    izq, der = st.columns(2, gap="large")
    with izq:
        C.ayuda("Algunos ensayos requieren espera: las muestras pendientes se entregan cuando termina el turno programado. "   # PAT 134: ayuda «?»
                "Avanzar un turno usa la meta, la compra y el mantenimiento de la pestaña Operación.", "Laboratorio virtual y especificaciones")
        a, b = st.columns(2)
        if a.button("Tomar muestra (ensayos ampliados)", disabled=op.finalizada, key="cal_muestra", width="stretch"):
            tomar_muestra(op, pl, "cal")
        if b.button("Avanzar un turno", disabled=op.finalizada, key="cal_turno", width="stretch"):
            ejecutar_turno(op, pl, "cal")
        if op.pendientes:
            st.warning("Ensayos pendientes: " + ", ".join(f"muestra {p['id']} (resultado en el turno {p['entrega']})" for p in op.pendientes))
        else:
            st.caption("No hay ensayos pendientes.")
        ult = op.lab[-1]["valores"] if op.lab else {}
        AT.tabla("cal_lab", "Último resultado de cada ensayo")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=v.nombre, u=C.fmt(ult.get(v.id), v.decimales) + (f" {v.unidad}" if v.unidad and v.id in ult else "") if v.id in ult else "—",
                              e=v.especificacion(), st=_estado(v, ult.get(v.id))) for v in vs],
                        [("n", "Ensayo", "txt", 0), ("u", "Último resultado", "cen", 0), ("e", "Especificación", "txt", 0), ("st", "Estado", "txt", 0)])
        C.ayuda("Las acciones son parámetros de la planta: cambian la calidad de las próximas muestras y también el "
                "vapor, el gas y la recuperación de calor de las demás pestañas.", "Acciones correctivas")
        acc = Q.acciones(pl)
        if acc:
            with st.form("form_acciones"):
                nuevos = []
                for i, x in enumerate(acc):
                    nuevos.append(st.slider(x["etiqueta"], float(x["minimo"]), float(x["maximo"]), float(min(max(x["valor"], x["minimo"]), x["maximo"])),
                                            float(x["paso"]), key=f"acc_{pl.rubro}_{i}"))
                ok = st.form_submit_button("Aplicar acciones y recalcular la planta", type="primary", disabled=op.finalizada)
            if ok:
                n = sum(Q.aplicar_accion(pl, x, v) for x, v in zip(acc, nuevos))
                if n and C.resolver(pl):
                    op.acciones += n
                    ss.aviso_operacion = "cal", f"{n} acción(es) correctiva(s) aplicada(s); la planta se recalculó (vapor, gas y recuperación de calor incluidos)."
                    st.rerun()
    with der:
        st.markdown("#### Control estadístico de procesos (SPC)")
        idx = {v.id: v for v in vs}
        if ss.get("spc_var") not in idx:            # al cambiar de rubro cambian las variables
            ss.pop("spc_var", None)
        vid = st.selectbox("Variable", list(idx), format_func=lambda k: f"{idx[k].nombre} ({idx[k].unidad})" if idx[k].unidad else idx[k].nombre, key="spc_var")
        v = idx[vid]
        vals = [m["valores"][vid] for m in op.lab if vid in m["valores"]]
        r = OP.spc(vals, v.lo, v.hi)
        if vals:
            st.image(OP.grafico_control(vals, v, r), width="stretch")      # st.html no muestra SVG
            C.ayuda(":orange[Naranjo, trazos largos]: límites de especificación (LIE y LSE). :blue[Azul, trazos cortos]: límites de control "
                    "(LIC y LSC) con el rango móvil; gris: línea central. :red[Punto rojo]: fuera de especificación; borde amarillo: fuera de control.")
            k = st.columns(3) + st.columns(2)
            k[0].metric("Muestras", r["n"])
            k[1].metric("Media", C.fmt(r["media"], v.decimales + 1))
            k[2].metric("σ (rango móvil)", C.fmt(r["sigma"], v.decimales + 1), help=f"Desviación estándar de la muestra: {C.fmt(r['s'], v.decimales + 1)}")
            k[3].metric("Estado SPC", r["estado"])
            cpk = (f"{C.fmt(r['cp'], 2) if r['cp'] is not None else '—'} / {C.fmt(r['cpk'], 2) if r['cpk'] is not None else '—'}"
                   if r["reportable"] else "No informable")
            k[4].metric("Cp / Cpk", cpk, help=(f"Pp / Ppk con la desviación de la muestra: {C.fmt(r['pp'], 2) if r['pp'] is not None else '—'} / "
                                               f"{C.fmt(r['ppk'], 2) if r['ppk'] is not None else '—'}. Se informan con 12 muestras o más y sin señales."))
            C.ayuda("Los puntos fuera de 3σ y las rachas son detectores introductorios: no demuestran por sí solos la estabilidad; Cp y Cpk se "
                    "interpretan con cautela.")
        else:
            st.info("Todavía no hay resultados recibidos: tome muestras y avance turnos.")
        st.info("Los límites de especificación (lo que exige la norma o el cliente) son distintos de los límites de control (lo que el proceso "
                "hace por sí solo). Se necesitan al menos 8 muestras para estimar los límites de control y 12, sin señales, para informar Cp y Cpk.")
        bajos = [x for x in vs if OP.prob_conforme(x.media, x.sd * OP.factor_variabilidad(pl, x), x.lo, x.hi) < 0.75]
        for x in bajos:
            st.warning(f"La media de «{x.nombre}» ({C.fmt(x.media, x.decimales)} {x.unidad}) está en el límite o fuera de la especificación "
                       f"({x.especificacion()}): con la variabilidad común, gran parte del producto queda fuera. Mueva la consigna con las "
                       "acciones correctivas, dejando margen.")
        for x in [x for x in vs if getattr(x, "consigna", None) is not None]:   # PAT 135 (T8): banda de guarda
            st.caption(C.esc(f"«{x.nombre}»: el balance deja la consigna en {C.fmt(x.consigna, x.decimales)} {x.unidad}, justo en el límite "
                             f"({x.especificacion()}); el lazo opera con banda de guarda en {C.fmt(x.media, x.decimales)} {x.unidad} "
                             "(3 desviaciones estándar adentro, Cpk 1,0; Supuesto)."))
    with st.expander("Variables de calidad: medias, variabilidad y fuentes", expanded=False):
        AT.tabla("cal_variables", "Medias, variabilidad y fuentes")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=x.nombre, m=x.media, sd=x.sd * OP.factor_variabilidad(pl, x), p=100 * OP.prob_conforme(x.media, x.sd * OP.factor_variabilidad(pl, x), x.lo, x.hi),
                              e=x.especificacion(), c=x.categoria, fe=x.fuente_espec, fm=x.fuente_media) for x in vs],
                        [("n", "Variable", "txt", 0), ("m", "Media", "num", 2), ("sd", "Desviación estándar", "num", 3), ("p", "Dentro de especificación (%)", "num", 1),
                         ("e", "Especificación", "txt", 0), ("c", "Categoría del límite", "txt", 0), ("fe", "Fuente del límite", "txt", 0),
                         ("fm", "Origen de la media", "txt", 0)])
        st.caption("Desviaciones estándar de la variabilidad común: Supuestos didácticos (las del pellet son las del simulador del profesor); crecen con el "
                   "desgaste del equipo de control. Fracción conforme del turno = producto de las probabilidades de cada variable, con un máximo de 0,99.")
