"""Sección Datos de la planta de la pestaña Escenario (PAT 133, mejora 19): descargar la plantilla CSV de datos de placa y
mediciones, subirla llena, revisar el informe de validación y aplicar los valores medidos a la planta."""
from __future__ import annotations
import hashlib
import streamlit as st
from pat_sim.motor import datos_planta as DP
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def _tabla_cambios(cambios):
    AT.tabla("dp_cambios", "Valores que se aplicarían")   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(c, eqp=f"{c['equipo']} · {c['nombre_equipo']}", ant=f"{DP.texto_cl(c['antes']) or '—'} ({c['categoria_antes']})",
                          des=DP.texto_cl(c["despues"])) for c in cambios],
                    [("fila", "Fila", "num", 0), ("eqp", "Equipo", "txt", 0), ("nombre", "Parámetro", "txt", 0), ("ant", "Antes", "cen", 0),
                     ("des", "Medido", "cen", 0), ("unidad", "Unidad", "txt", 0), ("fuente", "Fuente", "txt", 0), ("fecha", "Fecha", "txt", 0),
                     ("nota", "Nota", "txt", 0)])


def mostrar():
    ss = st.session_state; pl = C.planta()
    C.ayuda("Reemplace los parámetros supuestos por datos medidos o de placa. Descargue la plantilla, llene la columna valor solo en "   # PAT 134: ayuda «?»
            "lo que tenga medido (con su unidad, fuente y fecha dd-mm-aaaa) y súbala. La plantilla usa punto y coma y coma decimal.",
            "Datos de placa y mediciones de la planta")
    DP.restaurar_medidos(pl)                     # una versión guardada con datos medidos recupera su categoría «Medido»
    a, b = st.columns(2)
    a.download_button("Descargar la plantilla (CSV)", DP.plantilla_csv(pl), file_name=f"Plantilla_datos_{pl.rubro}.csv",
                      mime="text/csv", key="dp_plantilla", width="stretch")
    arch = b.file_uploader("Subir la plantilla llena (CSV)", type=["csv", "txt"], key="dp_archivo")
    if arch is not None:
        try:
            datos = arch.getvalue()
        except AttributeError:
            datos = arch if isinstance(arch, (bytes, str)) else b""
        huella = hashlib.sha1(datos if isinstance(datos, bytes) else datos.encode()).hexdigest()
        try:
            filas = DP.leer_csv(datos)
        except Exception as e:                  # columnas faltantes o archivo ilegible
            st.error(f"No se pudo leer el archivo: {e}")
            filas = None
        if filas is not None:
            # vista previa sobre una copia: la planta de la sesión no cambia hasta presionar «Aplicar»
            from pat_sim.datos.bd import copiar_planta
            try:
                copia = copiar_planta(pl, resolver=pl.resuelta)
                for k, e in copia.equipos.items():          # la copia guarda solo valores: se le pasan la categoría y la fuente
                    for c, p in e.params.items():
                        o = pl.equipos[k].params.get(c)
                        if o is not None:
                            p.categoria, p.fuente, p.justificacion = o.categoria, o.fuente, o.justificacion
                prueba = DP.aplicar_datos(copia, filas)
            except Exception as e:
                st.error(f"No se pudo validar el archivo: {e}")
                prueba = None
            if prueba is not None:
                m1, m2, m3 = st.columns(3)
                m1.metric("Valores que se aplicarían", len(prueba["cambios"]))
                m2.metric("Filas rechazadas", len(prueba["rechazos"]))
                m3.metric("Filas sin valor (se ignoran)", prueba["ignoradas"])
                if prueba.get("error"):
                    st.error(prueba["error"])
                if prueba["cambios"]:
                    _tabla_cambios(prueba["cambios"])
                if prueba["rechazos"]:
                    AT.tabla("dp_rechazos", "Filas rechazadas")   # PAT 134: «?» de la tabla
                    C.mostrar_tabla(prueba["rechazos"], [("fila", "Fila", "num", 0), ("equipo", "Equipo", "txt", 0), ("parametro", "Parámetro", "txt", 0),
                                                         ("valor", "Valor", "cen", 0), ("unidad", "Unidad", "txt", 0), ("motivo", "Motivo", "txt", 0)])
                if prueba["cambios"] and not prueba.get("error"):
                    if ss.get("dp_aplicado") == huella:
                        st.success("Estos datos ya están aplicados a la planta.")
                    elif st.button("Aplicar los datos medidos a la planta", type="primary", key="dp_aplicar"):
                        inf = DP.aplicar_datos(pl, filas)
                        if inf.get("error"):
                            st.error(inf["error"])
                        else:
                            ss["dp_aplicado"] = huella; ss["dp_informe"] = inf
                            n = len(inf["cambios"])
                            st.success((f"Se aplicaron {n} valores medidos" if n > 1 else "Se aplicó 1 valor medido") + " y la planta se volvió a resolver. "
                                       "Guarde una versión para conservarlos.")
    med = DP.medidos(pl)
    if med:
        with st.expander(f"Parámetros medidos en la planta actual ({len(med)})"):
            AT.tabla("dp_medidos", "Parámetros medidos")   # PAT 134: «?» de la tabla
            C.mostrar_tabla([dict(m, eqp=f"{m['equipo']} · {m['nombre_equipo']}", v=DP.texto_cl(m["valor"])) for m in med],
                            [("eqp", "Equipo", "txt", 0), ("nombre", "Parámetro", "txt", 0), ("v", "Valor", "cen", 0), ("unidad", "Unidad", "txt", 0),
                             ("fuente", "Fuente y fecha", "txt", 0)])
