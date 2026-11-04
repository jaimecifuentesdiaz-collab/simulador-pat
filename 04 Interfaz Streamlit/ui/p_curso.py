"""Pestaña Curso (PAT 133, mejora 16): el estudiante ingresa su identificador y carga su variante del caso; el profesor,
con su clave, ve la tabla de puntajes y la exporta a CSV. Como el modo SCORM del simulador del profesor, pero con la
variante también en los datos de la planta y con las entregas guardadas en la base."""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.motor import curso as CU
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

CURSO_DEFECTO = "PAT UTAL"


def _cargar_variante(bd, curso, ident, nombre):
    ss = st.session_state
    var = CU.ingresar(bd, curso, ident, nombre)
    ss.pl = CU.crear_planta(var); ss.pid = None; ss.vid = None
    ss.op = CU.operacion_de(var)
    ss.pop("ev_estudiante", None)          # PAT 133: Evaluación toma el identificador desde op.estudiante
    ss.pop("op_compra", None)
    CU.aplicar_economia(var, ss.economia, C.HENRY_HUB, C.PRECIO_BIOMASA)
    for k in ("rc_dT", "rc_Tfin", "esc_rubro"):
        ss.pop(k, None)
    ss.cur_variante = var; ss.cur_curso = curso["nombre"]
    ss.aviso_curso = f"Cargada la variante de {var['identificador']} ({RUBROS[var['rubro']]}). Todas las pestañas trabajan con ella."


def _tabla_variante(var):
    filas = []
    for r in CU.RANGOS[var["rubro"]]:
        v = var["planta"].get(r.clave, var["economia"].get(r.clave))
        filas.append(dict(p=r.etiqueta, v=v, rango=f"{C.fmt(r.minimo, 3 if r.paso < 0.01 else 2 if r.paso < 1 else 0)} a "
                                                    f"{C.fmt(r.maximo, 3 if r.paso < 0.01 else 2 if r.paso < 1 else 0)}", f=r.fuente,
                          d=3 if r.paso < 0.01 else 2 if r.paso < 1 else 0))
    AT.tabla("cur_variante", "Parámetros de su variante")   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(f_, v=C.fmt(f_["v"], f_["d"])) for f_ in filas],
                    [("p", "Parámetro", "txt", 0), ("v", "Valor de su variante", "cen", 0), ("rango", "Rango del curso", "cen", 0), ("f", "Fuente", "txt", 0)])
    st.caption(f"Semilla de la operación: {var['semilla']} (la misma que fija su identificador en la pestaña Evaluación).")


def mostrar():
    ss = st.session_state; bd = C.obtener_bd(); pl = C.planta()
    st.subheader("Curso")
    from . import s_itinerario                                 # PAT 134: el itinerario estaba en la barra lateral
    s_itinerario.mostrar()
    st.divider()
    if ss.get("aviso_curso"):
        st.success(ss.pop("aviso_curso"))
    nombre_curso = st.text_input("Curso", value=ss.get("cur_curso", CURSO_DEFECTO), key="cur_nombre_curso",
                                 help="El mismo nombre que le indicó su profesor: la variante depende del curso y del identificador.").strip() or CURSO_DEFECTO
    curso = bd.obtener_curso(nombre_curso)
    izq, der = st.columns(2, gap="large")
    with izq:
        st.markdown("#### Estudiante")
        if curso is None:
            st.caption(f"El curso «{nombre_curso}» todavía no existe: se crea con el rubro de la planta actual ({RUBROS.get(pl.rubro, pl.rubro)}) al cargar la primera variante.")
        else:
            st.caption(f"Rubro del curso: {RUBROS.get(curso['rubro'], curso['rubro'])}")
        ident = st.text_input("Identificador del estudiante (RUT o correo institucional)", key="cur_ident")
        nombre = st.text_input("Nombre (opcional)", key="cur_nombre_est")
        if st.button("Cargar mi variante", type="primary", disabled=not CU.normalizar(ident), key="cur_cargar", width="stretch"):
            try:
                if curso is None:
                    curso = CU.configurar(bd, nombre_curso, pl.rubro if pl.rubro in CU.RANGOS else "tomate")
                _cargar_variante(bd, curso, ident, nombre)
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo cargar la variante: {e}")
        var = ss.get("cur_variante")
        if var:
            st.markdown(f"**Variante cargada:** {var['identificador']}")
            _tabla_variante(var)
            op = C.operacion()
            listo = bool(op.finalizada and op.puntaje and op.estudiante == var["identificador"])
            if st.button("Entregar el puntaje de la Evaluación", disabled=not listo or curso is None, key="cur_entregar", width="stretch"):
                try:
                    CU.entregar(bd, curso, var["identificador"], op)
                    st.success(f"Entrega registrada: {op.puntaje['total']} de 100 puntos.")
                except Exception as e:
                    st.error(str(e))
            if not listo:
                st.caption("Para entregar, finalice la evaluación en la pestaña Evaluación con esta variante cargada.")
    with der:
        st.markdown("#### Profesor")
        clave = st.text_input("Clave del profesor", type="password", key="cur_clave")
        if curso is None or not curso.get("clave_hash"):
            rub = st.selectbox("Rubro del curso", list(CU.RANGOS), index=list(CU.RANGOS).index(pl.rubro) if pl.rubro in CU.RANGOS else 0,
                               format_func=lambda k: RUBROS[k], key="cur_rubro")
            if st.button("Crear el curso y fijar la clave", disabled=len(clave) < 6, key="cur_fijar", width="stretch"):
                CU.configurar(bd, nombre_curso, rub, clave)
                st.success("Clave fijada. Se guarda solo como hash SHA-256 con sal.")
                st.rerun()
            st.caption("La clave necesita 6 caracteres o más. Una vez fijada, solo quien la conoce ve los puntajes.")
            return
        if not clave:
            st.caption("Ingrese la clave para ver los puntajes del curso.")
            return
        try:
            filas = CU.tabla_profesor(bd, curso, clave)
        except PermissionError as e:
            st.error(str(e))
            return
        st.metric("Estudiantes inscritos", len(filas))
        AT.tabla("cur_profesor", "Puntajes del curso")   # PAT 134: «?» de la tabla
        C.mostrar_tabla(filas, [("identificador", "Identificador", "txt", 0), ("nombre", "Nombre", "txt", 0), ("entregas", "Entregas", "num", 0),
                                ("ultimo", "Último puntaje", "num", 0), ("mejor", "Mejor puntaje", "num", 0), ("fecha", "Fecha", "txt", 0)])
        st.download_button("Exportar puntajes (CSV)", CU.exportar_csv(filas), file_name=f"Puntajes_{nombre_curso.replace(' ', '_')}.csv",
                           mime="text/csv", key="cur_csv", width="stretch")
