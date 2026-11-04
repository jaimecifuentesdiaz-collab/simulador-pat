"""Pantalla Mantenedor (PAT 135, tarea T7.4): función reservada al profesor (reunión del 04-11-2026, indicación 5).

Con la clave del profesor se crean, editan y activan los desafíos y se editan los parámetros (CEPCI, dólar, precios de
energía), el catálogo de equipos y la simbología, todo guardado en la base de datos (datos/mantenedor.py). Sin la clave,
todo se ve en solo lectura. La clave se compara por su SHA-256 con st.secrets["PROFESOR_CLAVE_SHA256"] o con la variable de
entorno del mismo nombre; si ninguna existe (o está vacía), con el hash de respaldo del código (clave «torres2026»).
"""
from __future__ import annotations
import html, os, re
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.datos import mantenedor as M
from pat_sim.motor import desafio as D
from . import comun as C

NUEVO = "(nuevo desafío)"
AYUDA = """
**Para qué sirve.** Es la función reservada al profesor: cargar las instrucciones del ejercicio o cambiar lo que quiera que
sea distinto. Lo que se guarda aquí queda en la base de datos y lo leen las demás pantallas (por ejemplo, Desafío).

**Clave.** Se compara su SHA-256 con PROFESOR_CLAVE_SHA256 de los secretos de Streamlit o de las variables de entorno. Si no
hay ninguno, vale la clave de respaldo del código; cámbiela en `.streamlit/secrets.toml` antes de publicar la aplicación.

**Cómo editar.** Cada pestaña tiene una tabla editable: cambie las celdas, agregue filas con «+» y presione Guardar. Cada
cifra debe llevar su fuente (autor, año, página o tabla) o la palabra «Supuesto» con su justificación.

**Desafíos.** El enunciado se lee después del saludo: «don Jaime Cifuentes, su desafío es …», así que conviene empezar con
un verbo (por ejemplo «diseñar una planta de secado de agar agar …»). Solo los desafíos activos aparecen en la pantalla Desafío.
"""


# ---------------------------------------------------------------- utilidades
def _col(tipo: str, titulo: str, alineacion: str | None = None, **kw):
    """Columna del editor con alineación (texto a la izquierda, números al centro, plata a la derecha). Si la versión de
    Streamlit no acepta «alignment», se crea sin ella."""
    fn = getattr(st.column_config, tipo)
    if alineacion:
        try:
            return fn(titulo, alignment=alineacion, **kw)
        except TypeError:
            pass
    return fn(titulo, **kw)


def _editor(filas: list[dict], columnas: list[str], key: str, config: dict | None = None, dinamico: bool = True,
            deshabilitar: list[str] | None = None) -> list[dict]:
    """st.data_editor sobre un DataFrame; devuelve la lista de filas editadas (las originales si el editor no devuelve nada)."""
    import pandas as pd
    df0 = pd.DataFrame(filas, columns=columnas)
    df = st.data_editor(df0, key=key, column_config=config or {}, hide_index=True, width="stretch",
                        num_rows="dynamic" if dinamico else "fixed", disabled=deshabilitar or [])
    df = df0 if df is None else df
    return [{k: (None if _vacio(v) else v) for k, v in r.items()} for r in df.to_dict("records")]


def _vacio(v) -> bool:
    try:
        return v is None or (isinstance(v, float) and v != v)
    except Exception:
        return False


def _es_plata(unidad: str) -> bool:
    return "$" in (unidad or "")


def _valor_txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "verdadero" if v else "falso"
    if isinstance(v, (int, float)):
        return C.fmt(v, 0) if float(v).is_integer() else C.fmt(v, 6).rstrip("0").rstrip(",")
    return str(v)


def _leer_valor(texto, original):
    """Texto del editor al tipo del valor original (número con coma decimal, verdadero/falso o texto)."""
    t = "" if texto is None else str(texto).strip()
    if t == "":
        return None
    if isinstance(original, bool):
        return t.lower() in ("verdadero", "true", "sí", "si", "1")
    if isinstance(original, str):
        return t
    try:
        if "," in t or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):     # formato chileno: 1.234,5 o 450.000
            x = float(t.replace(".", "").replace(",", "."))
        else:
            x = float(t)
    except ValueError:
        return t
    return int(x) if isinstance(original, int) and x.is_integer() else x


def _valida(key: str, opciones: list):
    """Si el valor guardado de un selector ya no está entre las opciones (se borró o cambió el filtro), se olvida."""
    if key in st.session_state and st.session_state[key] not in opciones:
        st.session_state.pop(key, None)


def _acceso() -> bool:
    try:
        secretos = st.secrets
    except Exception:
        secretos = None
    esperado, origen = M.hash_esperado(secretos, os.environ)
    clave = st.text_input("Clave del profesor", type="password", key="man_clave",
                          help="Sin la clave, el mantenedor queda en solo lectura.")
    ok = M.verificar_profesor(clave, esperado)
    if clave and not ok:
        st.error("Clave incorrecta: el mantenedor queda en solo lectura.")
    elif ok:
        st.success("Acceso de profesor: puede editar y guardar.")
        if origen == "defecto":
            st.warning("Se usa la clave de respaldo del código. Fije PROFESOR_CLAVE_SHA256 en .streamlit/secrets.toml antes de publicar.")
    else:
        st.info("Ingrese la clave del profesor para editar. Mientras tanto, todo se ve en solo lectura.")
    return ok


# ---------------------------------------------------------------- desafíos
def _tab_desafios(m, ok: bool):
    ds = m.listar_desafios()
    filas = []
    for d in ds:
        try:
            e = D.estadisticas(d); per, tot, u = e["n"], e["total"], d["demanda"]["unidad"]
        except ValueError:
            per, tot, u = None, None, ""
        filas.append(dict(t=d["titulo"], p=d["producto"], r=RUBROS.get(d["rubro"], d["rubro"]), n=per, tot=tot, u=u,
                          a="Sí" if d["activo"] else "No", au=d.get("autor", ""), f=d.get("fecha", "")))
    C.mostrar_tabla(filas, [("t", "Título", "txt", 0), ("p", "Producto", "txt", 0), ("r", "Rubro", "txt", 0), ("n", "Períodos", "num", 0),
                            ("tot", "Demanda total", "num", 1), ("u", "Unidad", "txt", 0), ("a", "Activo", "txt", 0),
                            ("au", "Autor", "txt", 0), ("f", "Fecha", "txt", 0)])
    if not ok:
        return
    st.markdown("##### Activar o desactivar")
    act = _editor([{"id": d["id"], "Título": d["titulo"], "Activo": bool(d["activo"])} for d in ds], ["id", "Título", "Activo"],
                  "man_activos", {"id": None, "Título": _col("TextColumn", "Título", "left"), "Activo": _col("CheckboxColumn", "Activo", "center")},
                  dinamico=False, deshabilitar=["Título"])
    if st.button("Guardar activación", key="man_guardar_activos"):
        for r in act:
            if r.get("id") is not None:
                m.activar_desafio(int(r["id"]), bool(r.get("Activo")))
        st.success("Activación guardada.")

    st.markdown("##### Crear o editar un desafío")
    opciones = [NUEVO] + [d["titulo"] for d in ds]
    _valida("man_des_sel", opciones)
    sel = st.selectbox("Desafío a editar", opciones, key="man_des_sel")
    d0 = next((d for d in ds if d["titulo"] == sel), None) or dict(
        id=None, titulo="", producto="", rubro="general", enunciado="diseñar una planta de ", autor="", activo=True,
        demanda=dict(periodo="mes", unidad="t", valores=[], etiquetas=[], fuente="Supuesto: "), precios=[])
    k = f"_{d0['id'] or 'nuevo'}"
    a, b = st.columns(2)
    titulo = a.text_input("Título", d0["titulo"], key="man_titulo" + k)
    producto = b.text_input("Producto", d0["producto"], key="man_producto" + k)
    rubros = list(RUBROS) + ["todos"]
    rubro = a.selectbox("Rubro de la planta", rubros, index=rubros.index(d0["rubro"]) if d0["rubro"] in rubros else 0,
                        format_func=lambda r: RUBROS.get(r, "Todos los equipos (ISO 10628)"), key="man_rubro" + k)
    autor = b.text_input("Autor", d0.get("autor", ""), key="man_autor" + k)
    enunciado = st.text_area("Enunciado (se lee después de «don Jaime Cifuentes, su desafío es»)", d0["enunciado"], key="man_enunciado" + k)
    activo = st.checkbox("Activo", bool(d0.get("activo", True)), key="man_activo" + k)
    dem = d0["demanda"]
    a, b = st.columns(2)
    periodos = list(D.PERIODOS); unidades = list(D.UNIDADES)
    periodo = a.selectbox("Período de la demanda", periodos, index=periodos.index(dem.get("periodo")) if dem.get("periodo") in periodos else 4,
                          key="man_periodo" + k)
    unidad = b.selectbox("Unidad de la demanda", unidades, index=unidades.index(dem.get("unidad")) if dem.get("unidad") in unidades else 1,
                         key="man_unidad" + k)
    fuente = st.text_input("Fuente de la demanda (o «Supuesto» con su justificación)", dem.get("fuente", ""), key="man_fuente" + k)
    vals = dem.get("valores") or []; et = dem.get("etiquetas") or [str(i + 1) for i in range(len(vals))]
    st.caption("Demanda por período (una fila por período, en orden)")
    fd = _editor([{"Período": e, "Demanda": v} for e, v in zip(et, vals)], ["Período", "Demanda"], "man_dem" + k,
                 {"Período": _col("TextColumn", "Período", "left"), "Demanda": _col("NumberColumn", f"Demanda ({unidad})", "center", min_value=0.0)})
    st.caption("Precios de venta")
    fp = _editor([{"Producto": p.get("producto"), "Precio": p.get("precio"), "Moneda": p.get("moneda"), "Unidad": p.get("unidad"),
                   "Fuente": p.get("fuente")} for p in d0.get("precios") or []], ["Producto", "Precio", "Moneda", "Unidad", "Fuente"], "man_pre" + k,
                 {"Producto": _col("TextColumn", "Producto", "left"), "Precio": _col("NumberColumn", "Precio", "right", min_value=0.0),
                  "Moneda": _col("SelectboxColumn", "Moneda", "left", options=list(D.MONEDAS)), "Unidad": _col("TextColumn", "Unidad", "left"),
                  "Fuente": _col("TextColumn", "Fuente", "left")})
    nuevo = dict(id=d0["id"], titulo=titulo, producto=producto, rubro=rubro, enunciado=enunciado, autor=autor, activo=activo,
                 demanda=dict(periodo=periodo, unidad=unidad, fuente=fuente,
                              valores=[r["Demanda"] for r in fd if r.get("Demanda") is not None],
                              etiquetas=[str(r.get("Período") or i + 1) for i, r in enumerate(fd) if r.get("Demanda") is not None]),
                 precios=[dict(producto=r.get("Producto") or "", precio=r.get("Precio"), moneda=r.get("Moneda"), unidad=r.get("Unidad") or "",
                               fuente=r.get("Fuente") or "") for r in fp if any(r.get(c) not in (None, "") for c in ("Producto", "Precio"))])
    if st.button("Guardar desafío", type="primary", key="man_guardar_des" + k):
        err = D.validar(nuevo)
        if err:
            st.error("No se guardó: " + "; ".join(err))
        else:
            try:
                i = m.guardar_desafio(nuevo)
                st.success(f"Desafío «{titulo}» guardado (número {i}).")
            except (ValueError, KeyError) as e:
                st.error(f"No se guardó: {e}")
    if d0["id"] is not None:
        conf = st.checkbox("Confirmo que quiero eliminar este desafío", key="man_conf_borrar" + k)
        if st.button("Eliminar desafío", disabled=not conf, key="man_borrar_des" + k):
            m.eliminar_desafio(int(d0["id"]))
            st.success(f"Desafío «{d0['titulo']}» eliminado.")


# ---------------------------------------------------------------- parámetros
def _tab_parametros(m, ok: bool):
    ps = m.listar_parametros()
    cols = lambda tipo: [("clave", "Clave", "txt", 0), ("nombre", "Parámetro", "txt", 0), ("valor", "Valor", tipo, 4 if tipo == "num" else 2),
                         ("unidad", "Unidad", "txt", 0), ("fuente", "Fuente", "txt", 0), ("fecha", "Fecha", "txt", 0)]
    st.markdown("##### Precios")
    C.mostrar_tabla([p for p in ps if _es_plata(p["unidad"])], cols("mm"))
    st.markdown("##### Índices y factores")
    C.mostrar_tabla([p for p in ps if not _es_plata(p["unidad"])], cols("num"))
    if not ok:
        return
    st.markdown("##### Editar")
    nombres = ["clave", "nombre", "valor", "unidad", "categoria", "fuente", "fecha"]
    filas = _editor([{c: p.get(c) for c in nombres} for p in ps], nombres, "man_param",
                    {"clave": _col("TextColumn", "Clave", "left", required=True), "nombre": _col("TextColumn", "Parámetro", "left"),
                     "valor": _col("NumberColumn", "Valor", "center", format="%.4f"), "unidad": _col("TextColumn", "Unidad", "left"),
                     "categoria": _col("TextColumn", "Categoría", "left"), "fuente": _col("TextColumn", "Fuente", "left"),
                     "fecha": _col("TextColumn", "Fecha (AAAA-MM-DD)", "left")})
    if st.button("Guardar parámetros", type="primary", key="man_guardar_param"):
        err, vistas = [], set()
        for r in filas:
            if not r.get("clave"):
                continue
            vistas.add(str(r["clave"]).strip())
            if not str(r.get("fuente") or "").strip():
                err.append(f"{r['clave']}: falta la fuente (o «Supuesto» con su justificación)"); continue
            try:
                m.guardar_parametro(r["clave"], r.get("valor"), r.get("unidad") or "", r.get("fuente") or "", r.get("fecha") or "",
                                    r.get("nombre") or "", r.get("categoria") or "")
            except ValueError as e:
                err.append(str(e))
        quitadas = [p["clave"] for p in ps if p["clave"] not in vistas]
        for c in quitadas:                     # filas borradas en el editor
            m.eliminar_parametro(c)
        (st.error if err else st.success)("; ".join(err) if err else
                                          f"Parámetros guardados{' y eliminados: ' + ', '.join(quitadas) if quitadas else ''}.")


# ---------------------------------------------------------------- catálogo de equipos
def _tab_catalogo(m, ok: bool):
    rubros = list(RUBROS) + ["todos"]
    a, b = st.columns(2)
    rubro = a.selectbox("Rubro", rubros, format_func=lambda r: RUBROS.get(r, "Todos los equipos (ISO 10628)"), key="man_cat_rubro")
    eqs = m.listar_catalogo(None if rubro == "todos" else rubro)
    if not eqs:
        st.info("El catálogo está vacío en la base. Se llena con sembrar() al iniciar la aplicación.")
        return
    tipos = [e["tipo"] for e in eqs]
    _valida("man_cat_tipo", tipos)
    tipo = b.selectbox("Tipo de equipo", tipos, format_func=lambda t: next(e["nombre"] for e in eqs if e["tipo"] == t) + f" ({t})",
                       key="man_cat_tipo")
    e = next((x for x in eqs if x["tipo"] == tipo), eqs[0]); tipo = e["tipo"]
    st.caption(C.esc(f"Símbolo ISO 10628: {e['simbolo']}; categoría {e.get('iso_categoria')} de la Tabla C.1, letra {e.get('iso_letra')}. "
                     f"Origen: {e.get('fuente', '')}"))
    filas = [dict(p, vt=_valor_txt(p.get("valor"))) for p in e["parametros"]]
    C.mostrar_tabla(filas, [("clave", "Clave", "txt", 0), ("nombre", "Parámetro", "txt", 0), ("vt", "Valor por defecto", "cen", 0),
                            ("unidad", "Unidad", "txt", 0), ("categoria", "Categoría", "txt", 0), ("fuente", "Fuente", "txt", 0)])
    if not ok:
        return
    st.markdown("##### Editar")
    a, b = st.columns(2)
    nombre = a.text_input("Nombre del tipo", e["nombre"], key=f"man_cat_nombre_{tipo}")
    simbolos = [s["codigo"] for s in m.listar_simbolos("ISO 10628")] or [e["simbolo"]]
    simbolo = b.selectbox("Símbolo ISO 10628", simbolos, index=simbolos.index(e["simbolo"]) if e["simbolo"] in simbolos else 0,
                          key=f"man_cat_simbolo_{tipo}")
    nombres = ["clave", "nombre", "valor", "unidad", "categoria", "fuente", "justificacion", "minimo", "maximo"]
    ed = _editor([dict({c: p.get(c) for c in nombres}, valor=_valor_txt(p.get("valor"))) for p in e["parametros"]], nombres, f"man_cat_{tipo}",
                 {"clave": _col("TextColumn", "Clave", "left"), "nombre": _col("TextColumn", "Parámetro", "left"),
                  "valor": _col("TextColumn", "Valor por defecto", "center"), "unidad": _col("TextColumn", "Unidad", "left"),
                  "categoria": _col("TextColumn", "Categoría", "left"), "fuente": _col("TextColumn", "Fuente", "left"),
                  "justificacion": _col("TextColumn", "Justificación", "left"), "minimo": _col("NumberColumn", "Mínimo", "center"),
                  "maximo": _col("NumberColumn", "Máximo", "center")}, dinamico=False, deshabilitar=["clave"])
    if st.button("Guardar tipo de equipo", type="primary", key=f"man_cat_guardar_{tipo}"):
        orig = {p["clave"]: p for p in e["parametros"]}
        ps = []
        for r in ed:
            o = orig.get(r.get("clave"), {})
            ps.append(dict(o, **{c: r.get(c) for c in nombres if c != "valor"}, valor=_leer_valor(r.get("valor"), o.get("valor"))))
        sin_fuente = [p["clave"] for p in ps if p.get("valor") is not None and not str(p.get("fuente") or "").strip()
                      and str(p.get("categoria") or "") not in ("Usuario",)]
        if sin_fuente:
            st.error("Falta la fuente (o «Supuesto» con su justificación) en: " + ", ".join(sin_fuente))
        else:
            m.guardar_equipo(tipo, e["rubro"], nombre, simbolo, ps, e.get("fuente", ""), e.get("rubros"), e.get("iso_categoria"), e.get("iso_letra", ""))
            st.success(f"Tipo «{nombre}» guardado. Los equipos nuevos de este tipo toman estos valores con mantenedor.aplicar_defectos().")


# ---------------------------------------------------------------- símbolos
def _vista_svg(s: dict) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 60 60" '
            f'style="background:#fff;border:1px solid #ddd;border-radius:6px">{s.get("svg", "")}</svg>')


def _tab_simbolos(m, ok: bool):
    normas = m.normas()
    if not normas:
        st.info("No hay símbolos en la base. Se llenan con sembrar() al iniciar la aplicación.")
        return
    a, b = st.columns(2)
    _valida("man_sim_norma", normas)
    norma = a.selectbox("Norma", normas, index=normas.index("ISO 10628") if "ISO 10628" in normas else 0, key="man_sim_norma")
    ss_ = m.listar_simbolos(norma)
    C.mostrar_tabla(ss_, [("codigo", "Código", "txt", 0), ("nombre", "Nombre", "txt", 0), ("categoria", "Categoría", "txt", 0),
                          ("letra", "Letra", "txt", 0), ("fuente", "Fuente", "txt", 0)])
    con_dibujo = [s for s in ss_ if s.get("svg")]
    if con_dibujo:
        _valida("man_sim_ver", [s["codigo"] for s in con_dibujo])
        cod = b.selectbox("Ver símbolo", [s["codigo"] for s in con_dibujo], key="man_sim_ver")
        s = next((x for x in con_dibujo if x["codigo"] == cod), con_dibujo[0])
        st.html(_vista_svg(s) + f'<div class="nota">{html.escape(s["nombre"])}</div>')
    if not ok:
        return
    st.markdown("##### Editar")
    nombres = ["codigo", "nombre", "categoria", "letra", "svg", "fuente"]
    ed = _editor([{c: s.get(c) for c in nombres} for s in ss_], nombres, f"man_sim_{norma}",
                 {c: _col("TextColumn", t, "left") for c, t in zip(nombres, ("Código", "Nombre", "Categoría", "Letra", "Dibujo SVG (caja de 60 × 60)", "Fuente"))})
    if st.button("Guardar símbolos", type="primary", key=f"man_sim_guardar_{norma}"):
        par = {s["codigo"]: s.get("parametros") or {} for s in ss_}
        err = []
        for r in ed:
            if not r.get("codigo"):
                continue
            if not str(r.get("fuente") or "").strip():
                err.append(f"{r['codigo']}: falta la fuente"); continue
            try:
                m.guardar_simbolo(norma, r["codigo"], r.get("nombre") or "", r.get("categoria") or "", r.get("letra") or "", r.get("svg") or "",
                                  par.get(r["codigo"], {}), r.get("fuente") or "")
            except ValueError as e:
                err.append(str(e))
        (st.error if err else st.success)("; ".join(err) if err else "Símbolos guardados.")


# ---------------------------------------------------------------- pantalla
def mostrar():
    st.subheader("Mantenedor")
    with st.expander("?  Qué es el mantenedor y cómo se usa"):
        st.markdown(AYUDA)
    ok = _acceso()
    try:
        m = M.mantenedor(C.obtener_bd())
        if not m.contar()["catalogo_equipos"]:
            m.sembrar()
    except Exception as e:
        st.error(f"No se pudo abrir la base de datos del mantenedor: {e}")
        return
    t1, t2, t3, t4 = st.tabs(["Desafíos", "Parámetros", "Catálogo de equipos", "Símbolos"])
    with t1:
        _tab_desafios(m, ok)
    with t2:
        _tab_parametros(m, ok)
    with t3:
        _tab_catalogo(m, ok)
    with t4:
        _tab_simbolos(m, ok)
