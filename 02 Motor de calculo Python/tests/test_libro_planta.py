"""PAT 134: Excel de ida y vuelta de la planta (como las tablas globales y el Excel Import/Export de FlexSim)."""
import io, zipfile
from datetime import date
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import libro_planta as L
from pat_sim.motor import operacion as O
from pat_sim.motor.resumen import resumen_planta

HOY = date(2026, 11, 2)
DM = {"descarga_h": [1.1, 0.9, 1.3, 1.0, 1.2, 0.8], "falla_h": [3.0, 5.5, 2.0, 7.25, 4.0]}


def _valores(pl):
    return {(e.id, k): (p.valor, p.categoria, p.fuente) for e in pl.equipos.values() for k, p in e.params.items()}


def _editar(b: bytes, hoja: str, cambios: dict) -> bytes:
    """Cambia celdas de una hoja de la plantilla: {(fila, columna): valor} con valores de texto o número."""
    t = L.leer_xlsx(b); hs = []
    from pat_sim.motor import exportar as X
    for nombre, filas in t.items():
        h = X.Hoja(nombre, [12] * 10)
        for i, f in enumerate(filas, start=1):
            for j, v in enumerate(f, start=1):
                if v is not None:
                    h.poner(i, j, v)
        if nombre == hoja:
            for (i, j), v in cambios.items():
                h.poner(i, j, v)
        hs.append(h)
    return X.libro_xlsx(hs)


def _fila(t, hoja, eqid, clave=None):
    for i, f in enumerate(t[hoja], start=1):
        if f and f[0] == eqid and (clave is None or (len(f) > 2 and f[2] == clave)):
            return i
    raise AssertionError((hoja, eqid, clave))


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_ida_y_vuelta_sin_cambios_no_cambia_nada(mod):
    pl = mod.crear(); antes = _valores(pl)
    b = L.plantilla_xlsx(pl, datos_medidos=DM, fecha="02-11-2026")
    t = L.leer_xlsx(b)
    assert list(t) == list(L.HOJAS)
    v = L.validar(pl, t, datos_medidos=DM)
    assert v["errores"] == [] and v["cambios"] == [] and v["planta"] == []
    assert v["temporada"] == L.temporada_base(pl) and v["economia"] == L.economia_base()
    assert v["datos_medidos"] == DM
    assert L.aplicar(pl, v, hoy=HOY) == []
    assert _valores(pl) == antes and pl.resuelta


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_sin_paneles_inmovilizados_y_estilos(mod):
    pl = mod.crear(); r = resumen_planta(pl)
    for b in (L.plantilla_xlsx(pl), L.resultados_xlsx(pl, resumen=r, economia=L.economia_base())):
        z = zipfile.ZipFile(io.BytesIO(b))
        assert z.testzip() is None
        for n in z.namelist():
            if n.endswith(".xml") or n.endswith(".rels"):
                x = z.read(n).decode()
                assert "<pane" not in x and "frozen" not in x
        st = z.read("xl/styles.xml").decode()
        assert 'cellXfs count="18"' in st and st.count("<xf ") == 19 and 'horizontal="right"' in st


def test_plantilla_tiene_las_tablas():
    pl = agrozzi.crear(); t = L.leer_xlsx(L.plantilla_xlsx(pl, datos_medidos={"otra_serie": [1, 2, 3, 4, 5]}))
    enc = t["Parametros"][3]
    assert enc[:3] == ["Equipo", "Nombre del equipo", "Parámetro"] and "Fuente" in enc
    i = _fila(t, "Parametros", "W2", "eta")
    assert t["Parametros"][i - 1][4] == pytest.approx(0.80)
    assert ("W4", "brix_salida") not in {(f[0], f[2]) for f in t["Parametros"][4:] if len(f) > 2}     # lo ajusta una especificación
    assert any(f and f[0] == "F1" for f in t["Capacidades"][4:])
    tem = {f[0]: f for f in t["Temporada"][4:] if f}
    assert tem["camion"][2] == pytest.approx(25.0) and "Supuesto" in tem["camion"][4] and "pico" in tem
    eco = {f[0]: f for f in t["Economia"][4:] if f}
    assert eco["dolar"][2] == pytest.approx(990.35) and "Banco Central" in eco["dolar"][4]
    assert t["Datos medidos"][3] == ["descarga_h", "falla_h", "otra_serie"]
    assert "pico" not in {f[0] for f in L.leer_xlsx(L.plantilla_xlsx(pellet.crear()))["Temporada"][4:] if f}


def test_un_cambio_de_valor_llega_a_la_planta():
    pl = agrozzi.crear(); q0 = resumen_planta(pl)["Qsumidero"]
    b = L.plantilla_xlsx(pl); t = L.leer_xlsx(b)
    i = _fila(t, "Parametros", "W1", "T_salida"); j = _fila(t, "Capacidades", "F1")
    b2 = _editar(b, "Parametros", {(i, 5): "92,5", (i, 7): "Placa del TIC-101"})
    b2 = _editar(b2, "Capacidades", {(j, 3): 600.0})
    v = L.validar(pl, L.leer_xlsx(b2))
    assert v["errores"] == [] and len(v["planta"]) == 2
    det = L.aplicar(pl, v, hoy=HOY)
    assert len(det) == 2 and det[0].startswith("Planta: W1")
    p = pl.equipos["W1"].params["T_salida"]
    assert p.valor == pytest.approx(92.5) and p.categoria == "Usuario"
    assert p.fuente.startswith("Excel subido por el usuario, 02-11-2026") and "TIC-101" in p.fuente
    assert pl.equipos["F1"].v("capacidad") == pytest.approx(600.0)
    assert not pl.resuelta
    pl.resolver()
    assert resumen_planta(pl)["Qsumidero"] > q0
    assert L.deshacer(pl, v) == 2 and pl.equipos["W1"].v("T_salida") != pytest.approx(92.5)


def test_temporada_economia_y_datos_medidos_se_separan():
    pl = pellet.crear(); b = L.plantilla_xlsx(pl); t = L.leer_xlsx(b)
    it = next(i for i, f in enumerate(t["Temporada"], start=1) if f and f[0] == "camion")
    ie = next(i for i, f in enumerate(t["Economia"], start=1) if f and f[0] == "tasa")
    b = _editar(b, "Temporada", {(it, 3): "30,5"})
    b = _editar(b, "Economia", {(ie, 3): "0,08"})
    b = _editar(b, "Datos medidos", {(5, 1): 1.0, (6, 1): 1.5, (7, 1): "2,25", (8, 1): 0.75, (9, 1): 1.25})
    v = L.validar(pl, L.leer_xlsx(b))
    assert v["errores"] == []
    g = L.separar(v)
    assert g["planta"] == [] and len(g["temporada"]) == 1 and len(g["economia"]) == 1 and len(g["datos_medidos"]) == 1
    assert v["temporada"]["camion"] == pytest.approx(30.5) and v["temporada"]["base"] == "recepcion"
    assert v["economia"]["tasa"] == pytest.approx(0.08) and v["economia"]["dolar"] == pytest.approx(990.35)
    assert v["datos_medidos"] == {"descarga_h": [1.0, 1.5, 2.25, 0.75, 1.25]}
    det = L.aplicar(pl, v, hoy=HOY)
    assert any(d.startswith("Temporada:") for d in det) and any(d.startswith("Economía:") for d in det)
    assert any(d.startswith("Datos medidos:") for d in det) and pl.resuelta


def test_errores_detectados():
    pl = agrozzi.crear(); b = L.plantilla_xlsx(pl); t = L.leer_xlsx(b)
    i1 = _fila(t, "Parametros", "W2", "eta"); i2 = _fila(t, "Parametros", "W1", "T_salida"); i3 = _fila(t, "Parametros", "B1", "horas_dia")
    n = len(t["Parametros"])
    b = _editar(b, "Parametros", {(i1, 5): 1.5, (i2, 5): "abc", (i3, 5): 30.0, (n + 1, 1): "Z9", (n + 1, 3): "eta", (n + 1, 5): 1.0,
                                  (n + 2, 1): "W2", (n + 2, 3): "no_existe", (n + 2, 5): 1.0})
    it = next(i for i, f in enumerate(t["Temporada"], start=1) if f and f[0] == "camion")
    b = _editar(b, "Temporada", {(it, 3): -3.0})
    b = _editar(b, "Datos medidos", {(5, 2): 1.0, (6, 2): 2.0, (7, 2): 3.0})
    v = L.validar(pl, L.leer_xlsx(b)); e = " | ".join(v["errores"])
    assert "entre 0 y 1" in e or "máximo" in e
    assert "«abc» no es un número" in e
    assert "horas por día" in e or "máximo" in e
    assert "«Z9» no existe" in e and "no tiene el parámetro «no_existe»" in e
    assert "camion" in e and "fuera de rango" in e
    assert "falla_h tiene 3 valores" in e and "al menos 5" in e
    assert v["planta"] == [] and len(v["errores"]) == 7


def test_rango_negativos_y_horas():
    pl = pellet.crear(); B1 = pl.equipos["B1"]
    assert L._rango_param(B1.params["horas_dia"], 25) is not None
    assert L._rango_param(B1.params["horas_dia"], 24) is None
    cap = B1.params.get("capacidad") or next(e.params["capacidad"] for e in pl.equipos.values() if "capacidad" in e.params)
    assert "positiva" in L._rango_param(cap, -1) or "negativo" in L._rango_param(cap, -1)
    assert L._num("1.234,5") == pytest.approx(1234.5) and L._num("0,85") == pytest.approx(0.85) and L._num(" ") is None
    with pytest.raises(ValueError):
        L._num("doce")


def _xml(s):
    return s.encode("utf-8")


def test_libro_como_excel_con_sharedstrings_y_columnas_saltadas():
    """Libro hecho a mano como lo guarda Excel: sharedStrings con texto enriquecido, hojas en archivos con otro nombre y
    orden, columnas saltadas (sin celdas vacías escritas), filas sin atributo r en las celdas y una hoja renombrada."""
    pl = agrozzi.crear()
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    sst = ["Equipo", "Parámetro", "Valor", "W2", "eta", "W1", "T_salida", "Fuente", "Informe CFT", "descarga_h", "falla_h"]
    si = "".join(f"<si><t>{s}</t></si>" if s != "Valor" else "<si><r><rPr><b/></rPr><t>Val</t></r><r><t>or</t></r><rPh><t>x</t></rPh></si>" for s in sst)
    k = {s: i for i, s in enumerate(sst)}
    hoja_par = (f'<worksheet {ns}><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetData>'
                f'<row r="2"><c r="A2" t="s"><v>{k["Equipo"]}</v></c><c r="C2" t="s"><v>{k["Parámetro"]}</v></c>'
                f'<c r="E2" t="s"><v>{k["Valor"]}</v></c><c r="G2" t="s"><v>{k["Fuente"]}</v></c></row>'
                f'<row r="3"><c r="A3" t="s"><v>{k["W2"]}</v></c><c r="C3" t="s"><v>{k["eta"]}</v></c><c r="E3"><v>0.78</v></c>'
                f'<c r="G3" t="s"><v>{k["Informe CFT"]}</v></c></row>'
                f'<row r="5"><c r="A5" t="s"><v>{k["W1"]}</v></c><c r="C5" t="s"><v>{k["T_salida"]}</v></c><c r="E5" t="inlineStr"><is><t>91,5</t></is></c></row>'
                '</sheetData></worksheet>')
    hoja_dm = (f'<worksheet {ns}><sheetData><row r="1"><c t="s"><v>{k["descarga_h"]}</v></c><c t="s"><v>{k["falla_h"]}</v></c></row>'
               + "".join(f'<row r="{i}"><c r="A{i}"><v>{0.5 + i / 10}</v></c><c r="B{i}" t="str"><f>A{i}*2</f><v>{(0.5 + i / 10) * 2}</v></c></row>' for i in range(2, 8))
               + '</sheetData></worksheet>')
    wb = (f'<workbook {ns}><sheets><sheet name="Mis parámetros" sheetId="7" r:id="rId9"/><sheet name="Datos medidos" sheetId="3" r:id="rId2"/></sheets></workbook>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/hojaB.xml"/>'
            '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="/xl/worksheets/hojaA.xml"/>'
            '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            '</Relationships>')
    raiz = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("_rels/.rels", raiz); z.writestr("xl/workbook.xml", _xml(wb)); z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", _xml(f'<sst {ns} count="{len(sst)}">{si}</sst>'))
        z.writestr("xl/worksheets/hojaA.xml", _xml(hoja_par)); z.writestr("xl/worksheets/hojaB.xml", _xml(hoja_dm))
    t = L.leer_xlsx(buf.getvalue())
    assert list(t) == ["Mis parámetros", "Datos medidos"]
    assert t["Mis parámetros"][0] == [] and t["Mis parámetros"][1] == ["Equipo", None, "Parámetro", None, "Valor", None, "Fuente"]
    assert t["Mis parámetros"][3] == []                       # fila 4 no existe en el XML
    assert t["Mis parámetros"][4][4] == "91,5"
    assert t["Datos medidos"][0] == ["descarga_h", "falla_h"] and t["Datos medidos"][1][1] == "1.4"
    v = L.validar(pl, t)
    assert v["errores"] == []
    assert {(c["equipo"], c["parametro"]) for c in v["planta"]} == {("W2", "eta"), ("W1", "T_salida")}
    assert v["datos_medidos"]["descarga_h"] == pytest.approx([0.7, 0.8, 0.9, 1.0, 1.1, 1.2])
    assert v["datos_medidos"]["falla_h"] == pytest.approx([1.4, 1.6, 1.8, 2.0, 2.2, 2.4])
    assert v["temporada"] is None and v["economia"] is None
    L.aplicar(pl, v, hoy=HOY); pl.resolver()
    assert pl.equipos["W2"].v("eta") == pytest.approx(0.78) and "Informe CFT" in pl.equipos["W2"].params["eta"].fuente
    assert pl.equipos["W1"].v("T_salida") == pytest.approx(91.5)


def test_archivo_no_xlsx():
    with pytest.raises(ValueError):
        L.leer_xlsx(b"no es un zip")


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_resultados_de_corridas(mod):
    pl = mod.crear(); r = resumen_planta(pl)
    op = O.Operacion(rubro=pl.rubro, semilla=7)
    for _ in range(2):
        O.correr_turno(op, pl, resumen=r)
    dist = {"descarga_h": dict(nombre="gamma", parametros=dict(forma=2.0, escala=0.5)), "falla_h": dict(nombre="exponencial", parametros=[4.0], expresion="exponential(0, 4, 1)")}
    t = L.leer_xlsx(L.resultados_xlsx(pl, op=op, temporada={"semilla": 3}, economia=L.economia_base(), distribuciones=dist, resumen=r, fecha="02-11-2026"))
    assert list(t) == ["Leame", "Operación", "Temporada por día", "Distribuciones", "Recuperación"]
    assert t["Operación"][4][0] == pytest.approx(1.0) and t["Operación"][5][0] == pytest.approx(2.0)
    dias = [f for f in t["Temporada por día"] if f and isinstance(f[0], float) and len(f) > 5]
    assert len(dias) == round(float(pl.equipos["B1"].v("dias")))
    d = {f[0]: f for f in t["Distribuciones"][4:] if f}
    assert d["descarga_h"][3] == "gamma(2, 0.5)" and d["falla_h"][3] == "exponential(0, 4, 1)"


def test_resultados_sin_corridas():
    pl = chip.crear(); t = L.leer_xlsx(L.resultados_xlsx(pl))
    assert list(t) == ["Leame", "Operación", "Temporada por día", "Distribuciones"]
    assert "Sin turnos" in t["Operación"][3][0] and "Sin distribuciones" in t["Distribuciones"][3][0]
