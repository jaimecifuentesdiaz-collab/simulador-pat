"""PAT 133, mejora 18: el balance en .xlsx (sin dependencias) con fórmulas, y el informe listo para imprimir."""
import io, re, zipfile
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor.resumen import resumen_planta
from pat_sim.motor import exportar as X

E = dict(precio_gas=2.77, dolar=990.35, precio_biomasa=6750.0)


def _libro(mod):
    pl = mod.crear(); r = resumen_planta(pl)
    return pl, r, X.balance_xlsx(pl, r, E, fecha="02-11-2026")


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_xlsx_abre_con_zipfile_y_tiene_formulas(mod):
    pl, r, b = _libro(mod)
    z = zipfile.ZipFile(io.BytesIO(b))
    assert z.testzip() is None
    nombres = set(z.namelist())
    assert {"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"} <= nombres
    h1 = z.read("xl/worksheets/sheet1.xml").decode(); h2 = z.read("xl/worksheets/sheet2.xml").decode()
    assert "<f>SUMIF(" in h1                                   # total del calor de servicio
    f2 = re.findall(r"<f>([^<]+)</f>", h2)
    assert any(f.startswith("SUM(") for f in f2)              # oferta y total de la cascada
    assert any("/$E$5" in f for f in f2)                      # coberturas: división por el calor del sumidero
    assert sum(1 for f in f2 if f.startswith("$D$5*(")) == len(r["cascada_filas"])   # calor de cada etapa
    assert "<pane" not in h1 and "<pane" not in h2             # nunca paneles inmovilizados
    assert "wrapText" in z.read("xl/styles.xml").decode()


def test_valores_guardados_de_las_formulas_son_los_del_motor():
    pl, r, b = _libro(agrozzi)
    h2 = zipfile.ZipFile(io.BytesIO(b)).read("xl/worksheets/sheet2.xml").decode()
    tot = re.search(r"<c r=\"(E\d+)\" s=\"\d+\"><f>SUM\(E2\d:E2\d\)</f><v>([^<]+)</v>", h2)
    assert tot and float(tot.group(2)) == pytest.approx(r["cascada"], rel=1e-12)
    m = re.search(r"<c r=\"E5\" s=\"\d+\"><f>D5\*\(C5-B5\)</f><v>([^<]+)</v>", h2)
    assert m and float(m.group(1)) == pytest.approx(r["Qsumidero"], rel=1e-12)


def test_estilos_alineacion_texto_numero_dinero():
    _pl, _r, b = _libro(agrozzi)
    st = zipfile.ZipFile(io.BytesIO(b)).read("xl/styles.xml").decode()
    xfs = re.findall(r"<xf numFmtId[^>]*xfId=\"0\"[^>]*>(?:<alignment[^>]*/>)?</xf>", st)
    al = [re.search(r'horizontal="(\w+)"', x).group(1) for x in xfs]
    assert al[X.TXT] == "left" and al[X.NUM1] == "center" and al[X.PCT] == "center" and al[X.CLP] == "right" and al[X.TOT_CLP] == "right"
    assert 'fontId="1"' in xfs[X.ENC_TXT] and 'fontId="1"' in xfs[X.ENC_NUM]     # encabezados en negrita


def test_openpyxl_lo_lee_si_esta_instalado():
    try:
        import openpyxl
    except ImportError:
        return                                                  # en el entorno de Jaime no está: la prueba se omite
    pl, r, b = _libro(agrozzi)
    wb = openpyxl.load_workbook(io.BytesIO(b))
    assert wb.sheetnames == ["Corrientes", "Recuperación"]
    ws = wb["Recuperación"]
    assert ws.freeze_panes is None and wb["Corrientes"].freeze_panes is None
    assert ws["E5"].value == "=D5*(C5-B5)"
    assert ws["A1"].font.b and ws["B4"].alignment.horizontal == "center"
    v = openpyxl.load_workbook(io.BytesIO(b), data_only=True)["Recuperación"]["E5"].value
    assert v == pytest.approx(r["Qsumidero"], rel=1e-12)


def test_planta_sin_resolver_no_se_exporta():
    pl = agrozzi.crear(); pl.resuelta = False
    with pytest.raises(ValueError):
        X.balance_xlsx(pl, {})


def test_informe_imprimible():
    doc = "<!doctype html><html><head><title>x</title></head><body><h1>I</h1><h2>Equipos</h2><h2>Recuperación de calor</h2></body></html>"
    out = X.informe_imprimible(doc)
    assert "@media print" in out and "size:letter" in out and "window.print()" in out
    assert "Imprimir o guardar como PDF" in out
    assert out.index("barra-imprimir\"><button") > out.index("<body>")
    assert '<h2 class="salto">Recuperación de calor' in out and "<h2>Equipos</h2>" in out
