"""Pestaña Evaluación: justificaciones escritas y puntaje automático por criterios (PAT 130).

Como la pestaña «Evaluación» del simulador del profesor (grade y finishAssessment): la calificación no se muestra
mientras se trabaja; al finalizar se revela el puntaje y se bloquea la operación. Los 85 puntos del profesor (diseño,
restricciones, economía, calidad y operación) se mantienen y el PAT suma 15 puntos de recuperación de calor (total 100).
El informe docente (15 % en el profesor) se califica aparte con su rúbrica. Se descargan el informe (HTML) y el proyecto (JSON).
"""
from __future__ import annotations
import html as _h
import json
from datetime import datetime
import streamlit as st
from pat_sim.motor import operacion as OP
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

PREGUNTAS = [("restricciones", "Identifique la restricción y describa los cinco pasos de focalización"),
             ("calidad", "Explique los ajustes de calidad y las decisiones frente a las perturbaciones"),
             ("economia", "Justifique la alternativa económica seleccionada"),
             ("recuperacion", "Explique la recuperación de calor elegida y su efecto en el gas, las emisiones y la operación (aporte del PAT)")]

COMO = {"diseno": "15 si la planta está resuelta, produce y ningún equipo supera su capacidad efectiva; si no, 5",
        "restricciones": "10 si hay capacidades declaradas y una restricción identificada; 5 por la justificación escrita; 5 si la planta tiene 8 equipos o más",
        "economia": "10 si se ingresó la inversión en Economía; 5 si la recuperación de calor tiene resultado para calcular el VAN",
        "calidad": "10 con 8 resultados de laboratorio o más (5 con al menos uno); 5 si una muestra cumple todas las especificaciones; 5 si una variable tiene Cp y Cpk informables",
        "operacion": "10 con 5 turnos o más (5 con al menos uno); 5 si se hizo mantenimiento",
        "recuperacion": "10 si la cascada recupera calor; 5 por la justificación escrita"}
PESOS_PROFESOR = {"diseno": "15 %", "restricciones": "20 %", "economia": "15 %", "calidad": "20 %", "operacion": "15 %", "recuperacion": "No existe"}


def _contexto(pl):
    ss = st.session_state; r = C.resumen_o_nada()
    casc = None if not r or r.get("sin_sumidero") else float(r.get("cascada") or 0.0)
    return dict(inversion=float(ss.economia.get("inversion") or 0.0), cascada_kW=casc)


def informe_html(op, pl) -> str:
    """Informe descargable con las justificaciones, la operación y, si ya se finalizó, el puntaje."""
    e = lambda t: _h.escape(str(t))
    f = lambda v, d=1: C.fmt(v, d)
    filas = "".join(f"<tr><td class=c>{x['turno']}</td><td class=c>{f(x['producido'])}</td><td class=c>{f(100 * x['conformidad'])}</td>"
                    f"<td class=c>{f(x['vendido'])}</td><td class=c>{f(x['demanda'])}</td><td class=c>{f(x['faltante'])}</td>"
                    f"<td>{e(OP.MANTENIMIENTOS[x['mantenimiento']])}</td><td>{e('; '.join(x['eventos']))}</td></tr>" for x in op.turnos)
    puntaje = ""
    if op.puntaje:
        puntaje = ("<h2>Evaluación automática</h2><table><tr><th>Criterio</th><th class=c>Puntos</th><th class=c>Máximo</th></tr>"
                   + "".join(f"<tr><td>{e(n)}</td><td class=c>{op.puntaje[k]}</td><td class=c>{m}</td></tr>" for k, n, m in OP.CRITERIOS)
                   + f"<tr><th>Total</th><th class=c>{op.puntaje['total']}</th><th class=c>100</th></tr></table>"
                   "<p>Pendiente: rúbrica docente del informe. La evaluación automática usa indicadores de actividad y logros; no interpreta las justificaciones.</p>")
    just = "".join(f"<h3>{e(t)}</h3><p>{e(op.justificaciones.get(k, '')).replace(chr(10), '<br>') or '(sin respuesta)'}</p>" for k, t in PREGUNTAS)
    return (f"<!doctype html><html lang=es><head><meta charset=utf-8><title>Informe del simulador PAT</title><style>"
            "body{font-family:Arial,sans-serif;max-width:960px;margin:24px auto;color:#222}table{border-collapse:collapse;width:100%;font-size:13px}"
            "th,td{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left}.c{text-align:center}th{background:#eef3f0}</style></head><body>"
            f"<h1>Informe del simulador PAT</h1><p>Estudiante: {e(op.estudiante or 'sin nombre')} · Semilla: {op.semilla} · Planta: {e(pl.nombre)} · "
            f"Fecha: {datetime.now().strftime('%d-%m-%Y %H:%M')}</p>{puntaje}<h2>Justificación e informe técnico</h2>{just}"
            f"<h2>Turnos ejecutados</h2><table><tr><th class=c>Turno</th><th class=c>Producción (t)</th><th class=c>Conforme (%)</th>"
            f"<th class=c>Ventas (t)</th><th class=c>Demanda (t)</th><th class=c>Faltante (t)</th><th>Mantenimiento</th><th>Eventos</th></tr>{filas}</table>"
            f"<p>Resultados de laboratorio: {len(op.lab)}. Mantenimientos: {op.mantenimientos}. Acciones correctivas: {op.acciones}.</p></body></html>")


def mostrar():
    ss = st.session_state; pl = C.planta(); op = C.operacion()
    st.subheader("Evaluación")
    if ss.get("aviso_evaluacion"):
        st.success(ss.pop("aviso_evaluacion"))
    izq, der = st.columns(2, gap="large")
    with izq:
        st.markdown("#### Justificación e informe técnico")
        nombre = st.text_input("Nombre del estudiante (fija la semilla de su escenario)", value=op.estudiante, key="ev_estudiante",
                               disabled=bool(op.turnos), help="Como el simulador del profesor: el nombre define la semilla de las fallas, la demanda y "
                                                              "los resultados de laboratorio. Solo se puede cambiar antes del primer turno.")
        if not op.turnos and nombre.strip() != op.estudiante:
            op.estudiante = nombre.strip(); op.semilla = OP.semilla_texto(op.estudiante or "escenario")
        st.caption(f"Semilla del escenario: {op.semilla}")
        for k, t in PREGUNTAS:
            op.justificaciones[k] = st.text_area(t, value=op.justificaciones.get(k, ""), key=f"ev_{k}", height=110, disabled=op.finalizada)
        a, b = st.columns(2)
        a.download_button("Descargar informe (HTML)", informe_html(op, pl), file_name="Informe_simulador_PAT.html", mime="text/html", width="stretch")
        b.download_button("Descargar proyecto (JSON)", json.dumps(op.a_dict(), ensure_ascii=False, indent=1), file_name="Proyecto_operacion_PAT.json",
                          mime="application/json", width="stretch")
        sub = st.file_uploader("Importar un proyecto (JSON)", type=["json"], key="ev_importar")
        c, d = st.columns(2)
        if c.button("Cargar el proyecto importado", disabled=sub is None, width="stretch"):
            try:
                nuevo = OP.Operacion.desde_dict(json.loads(sub.getvalue().decode("utf-8")))
                if nuevo.rubro != pl.rubro:
                    raise ValueError(f"el proyecto es del rubro {nuevo.rubro} y la planta cargada es del rubro {pl.rubro}")
                ss.op = nuevo
                for k, _t in PREGUNTAS:
                    ss.pop(f"ev_{k}", None)
                ss.pop("ev_estudiante", None)
                ss.aviso_evaluacion = f"Proyecto importado: {len(nuevo.turnos)} turnos y {len(nuevo.lab)} resultados de laboratorio."
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo importar: {e}")
        if d.button("Reiniciar la práctica", width="stretch", help="Borra los turnos, el laboratorio y el puntaje; mantiene el nombre, la semilla y la planta."):
            ss.op = OP.Operacion(rubro=pl.rubro, semilla=op.semilla, estudiante=op.estudiante, justificaciones=dict(op.justificaciones))
            ss.pop("op_compra", None)
            ss.aviso_evaluacion = "Práctica reiniciada: la planta conserva el desgaste de los equipos (cárguela de nuevo en Escenario para partir en buen estado)."
            st.rerun()
    with der:
        C.ayuda("Durante el trabajo no se muestra la calificación. Al finalizar se revela el puntaje automático y se "   # PAT 134: ayuda «?»
                "bloquea la operación; el informe docente se califica aparte con su rúbrica.", "Evaluación combinada")
        k = st.columns(4)
        k[0].metric("Turnos", len(op.turnos)); k[1].metric("Resultados de laboratorio", len(op.lab))
        k[2].metric("Mantenimientos", op.mantenimientos); k[3].metric("Acciones correctivas", op.acciones)
        if not op.finalizada:
            if st.button("Finalizar y revelar evaluación", type="primary", disabled=not op.turnos, key="ev_finalizar", width="stretch"):
                try:
                    OP.finalizar(op, pl, **_contexto(pl))
                    ss.aviso_evaluacion = f"Evaluación finalizada: {op.puntaje['total']} de 100 puntos automáticos."
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if not op.turnos:
                st.caption("Ejecute al menos un turno antes de finalizar.")
        else:
            g = op.puntaje
            st.metric("Evaluación automática revelada", f"{g['total']} / 100")
            AT.tabla("ev_puntaje", "Puntaje por criterio")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(n=n, p=g[k_], m=m) for k_, n, m in OP.CRITERIOS] + [dict(n="Total", p=g["total"], m=100)],
                            [("n", "Criterio", "txt", 0), ("p", "Puntos obtenidos", "num", 0), ("m", "Máximo", "num", 0)])
            st.caption("Pendiente: rúbrica docente del informe.")
        with st.expander("Criterios y ponderaciones", expanded=False):
            AT.tabla("ev_criterios", "Criterios y ponderaciones")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(n=n, m=m, p=PESOS_PROFESOR[k_], c=COMO[k_]) for k_, n, m in OP.CRITERIOS],
                            [("n", "Criterio", "txt", 0), ("m", "Puntos en esta aplicación", "num", 0), ("p", "Peso en el simulador del profesor", "cen", 0),
                             ("c", "Cómo se mide", "txt", 0)])
            st.caption("El simulador del profesor registra 85 puntos automáticos normalizados a 100 y califica el informe docente (15 %) por separado. "
                       "Esta aplicación conserva sus cinco criterios y agrega 15 puntos de recuperación de calor, el aporte del PAT.")
