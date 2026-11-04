"""PAT 133, mejora 19: plantilla CSV de datos de placa y mediciones, validación y marca «Medido»."""
import csv, io
from datetime import date
import pytest
from pat_sim.escenarios import agrozzi, pellet
from pat_sim.motor import datos_planta as DP
from pat_sim.motor.resumen import resumen_planta

HOY = date(2026, 11, 2)


def _csv(filas):
    return "equipo;parametro;valor;unidad;fuente;fecha\r\n" + "\r\n".join(";".join(f) for f in filas)


def test_plantilla_formato_chileno():
    pl = agrozzi.crear(); t = DP.plantilla_csv(pl)
    assert t.startswith("﻿")
    filas = list(csv.reader(io.StringIO(t.lstrip("﻿")), delimiter=";"))
    assert filas[0][:6] == ["equipo", "parametro", "valor", "unidad", "fuente", "fecha"]
    claves = {(f[0], f[1]) for f in filas[1:]}
    assert ("W1", "T_salida") in claves and ("W2", "eta") in claves
    assert ("W4", "brix_salida") not in claves                 # lo ajusta la especificación de diseño
    assert all(f[2] == "" for f in filas[1:])
    ref = next(f[6] for f in filas[1:] if f[:2] == ["W2", "eta"])
    assert "0,8" in ref and "Supuesto" in ref                   # coma decimal y categoría actual


def test_aplicar_reemplaza_y_marca_medido():
    pl = agrozzi.crear(); antes = resumen_planta(pl)["Qsumidero"]
    inf = DP.aplicar_csv(pl, _csv([["W1", "T_salida", "92,5", "°C", "Placa del TIC-101", "15-10-2026"],
                                   ["W2", "eta", "78", "%", "Informe de mantención CFT", "01-10-2026"]]), hoy=HOY)
    assert not inf["rechazos"] and len(inf["cambios"]) == 2 and inf["resuelta"]
    p = pl.equipos["W1"].params["T_salida"]
    assert p.valor == pytest.approx(92.5) and p.categoria == "Medido" and p.fuente == "Placa del TIC-101, 15-10-2026"
    assert "90" in p.justificacion and "Agrozzi" in p.justificacion
    assert pl.equipos["W2"].v("eta") == pytest.approx(0.78)     # 78 % convertido a fracción
    assert resumen_planta(pl)["Qsumidero"] > antes              # el sumidero se recalculó con el valor medido
    c = next(x for x in inf["cambios"] if x["parametro"] == "eta")
    assert c["antes"] == pytest.approx(0.80) and c["despues"] == pytest.approx(0.78) and "convertido" in c["nota"]


@pytest.mark.parametrize("fila, motivo", [
    (["W9", "T_salida", "90", "°C", "x", "01-10-2026"], "no existe"),
    (["W1", "temperatura", "90", "°C", "x", "01-10-2026"], "no tiene ese parámetro"),
    (["W1", "T_salida", "120", "°C", "x", "01-10-2026"], "máximo"),
    (["W1", "T_salida", "90", "kPa", "x", "01-10-2026"], "unidad"),
    (["W1", "T_salida", "90", "°C", "", "01-10-2026"], "fuente"),
    (["W1", "T_salida", "90", "°C", "x", "01-12-2026"], "posterior"),
    (["W1", "T_salida", "noventa", "°C", "x", "01-10-2026"], "no es un número"),
    (["W4", "brix_salida", "0,27", "kg/kg", "x", "01-10-2026"], "especificación"),
    (["W4", "N", "3,5", "—", "x", "01-10-2026"], "entero"),
])
def test_rechazos_con_motivo(fila, motivo):
    pl = agrozzi.crear(); v0 = {k: dict((c, p.valor) for c, p in e.params.items()) for k, e in pl.equipos.items()}
    inf = DP.aplicar_csv(pl, _csv([fila]), hoy=HOY)
    assert not inf["cambios"] and len(inf["rechazos"]) == 1
    assert motivo in inf["rechazos"][0]["motivo"]
    assert {k: dict((c, p.valor) for c, p in e.params.items()) for k, e in pl.equipos.items()} == v0


def test_filas_vacias_repetidas_y_capacidad_en_biomasa():
    pl = pellet.crear()
    inf = DP.aplicar_datos(pl, DP.leer_csv(_csv([["T1", "capacidad", "12.500", "kg/h", "Placa del secador", "20-10-2026"],
                                                ["T1", "capacidad", "13", "t/h", "Otra", "20-10-2026"],
                                                ["Z1", "energia_especifica", "", "kWh/t", "", ""]])), hoy=HOY)
    assert inf["ignoradas"] == 1 and len(inf["cambios"]) == 1 and "repetido" in inf["rechazos"][0]["motivo"]
    assert pl.equipos["T1"].v("capacidad") == pytest.approx(12.5)    # 12.500 kg/h = 12,5 t/h
    assert DP.medidos(pl)[0]["parametro"] == "capacidad"


def test_si_no_resuelve_se_deshace_todo():
    # dentro del rango, pero el Longrun (W3) no puede salir más diluido que lo que le entrega el Apollo (8,5 °Brix)
    pl = agrozzi.crear(); t0 = pl.equipos["W3"].v("brix_salida"); t1 = pl.equipos["B1"].v("T")
    inf = DP.aplicar_csv(pl, _csv([["B1", "T", "20", "°C", "Termómetro", "01-10-2026"],
                                   ["W3", "brix_salida", "0,06", "kg/kg", "Refractómetro", "01-10-2026"]]), hoy=HOY)
    assert inf["error"] and not inf["cambios"] and len(inf["deshechos"]) == 2
    assert pl.equipos["W3"].v("brix_salida") == t0 and pl.equipos["W3"].params["brix_salida"].categoria == "Fabricante"
    assert pl.equipos["B1"].v("T") == t1 and pl.equipos["B1"].params["T"].categoria == "Supuesto"
    assert DP.CLAVE_GLOBAL not in pl.globales
    assert pl.resuelta


def test_marca_medido_sobrevive_a_guardar_y_cargar():
    from pat_sim.datos.bd import copiar_planta
    pl = agrozzi.crear()
    DP.aplicar_csv(pl, _csv([["B1", "T", "22", "°C", "Termómetro de recepción", "10-10-2026"]]), hoy=HOY)
    otra = copiar_planta(pl)
    assert otra.equipos["B1"].params["T"].categoria == "Supuesto"    # la versión guarda solo valores
    assert DP.restaurar_medidos(otra) == 1
    assert otra.equipos["B1"].params["T"].categoria == "Medido" and otra.equipos["B1"].v("T") == pytest.approx(22.0)


def test_numero_y_fecha_chilenos():
    assert DP.numero_cl("1.234,5") == pytest.approx(1234.5) and DP.numero_cl("0,85") == pytest.approx(0.85)
    assert DP.numero_cl("12.500") == pytest.approx(12500.0) and DP.numero_cl("0.125") == pytest.approx(0.125)
    assert DP.numero_cl("1.5") == pytest.approx(1.5) and DP.numero_cl("2.345.678") == pytest.approx(2345678.0)
    assert DP.fecha_cl("05-10-2026") == date(2026, 10, 5) and DP.fecha_cl("2026-10-05") == date(2026, 10, 5)
