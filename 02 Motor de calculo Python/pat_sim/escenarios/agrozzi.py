"""Escenario: línea de pasta de tomate de la planta basada en Agrozzi (Empresas Carozzi S.A., Teno).

Datos de la DIA 2025 y su Adenda (expediente SEIA), del fabricante de los evaporadores (CFT) y de la literatura,
como en Modelo_PAT_Agrozzi_v2.xlsx. Los nombres de los argumentos son los de model.py para poder contrastar."""
from __future__ import annotations
from ..motor.planta import Planta, EspecDiseno, Instrumento
from ..motor import recuperacion as rec, economia as eco
from ..catalogos import tomate as T
from ..catalogos.servicios import CalderaGas
from . import capacidades as _cap

BASE = dict(season=450000.0, days=76, hpd=24, rej=0.10, tom=0.04, xF=0.05, xA=0.085, xB=0.15, xP=0.30,
            Tin=25.0, Thb=90.0, cpt=3.98, cps=1.5, N=3, T1=75.0, TN=55.57, Ts=129.08,
            TbMVR=70.0, TcMVR=75.0, Tst=103.0, Tcool=40.0, Tfin=30.0, dT=5.0,
            tvr=True, Ra=1.0, dTtvr=10.0, flash=True, etaMVR=0.80)


def crear(capacidades=True, **kw) -> Planta:
    p = dict(BASE); p.update(kw)
    pl = Planta("Planta basada en Agrozzi: línea de pasta de tomate", "tomate")
    pl.globales.update(T_final_residual=p["Tfin"], dT_min=p["dT"])
    E = pl.agregar
    E(T.AlimentacionTomate("B1", "Recepción de tomate", 40, 120, temporada_t=p["season"], dias=p["days"], horas_dia=p["hpd"], T=p["Tin"], cp=p["cpt"]))
    E(T.RecepcionSeleccion("F1", "Lavado y selección", 200, 120, descarte=p["rej"]))
    E(T.Trituradora("Z1", "Trituradora", 360, 120))
    E(T.HotBreak("W1", "Hot break", 520, 120, T_salida=p["Thb"]))
    tom_ref = p["tom"] / (1 - p["rej"]) if p["rej"] < 1 else 0.0
    E(T.Refinadora("F2", "Refinadora", 680, 120, tomasa=tom_ref, brix_jugo=p["xF"], cps=p["cps"]))
    E(T.EvaporadorMVR("W2", "Apollo 40 (MVR)", 840, 120, brix_salida=p["xA"], T_ebullicion=p["TbMVR"], T_condensado=p["TcMVR"], eta=p["etaMVR"],
                      etiqueta_condensado="F4"))
    E(T.EvaporadorMVR("W3", "ART3MIS Longrun 60 (MVR)", 1000, 120, brix_salida=p["xB"], T_ebullicion=p["TbMVR"], T_condensado=p["TcMVR"], eta=p["etaMVR"],
                      etiqueta_condensado="F5"))
    E(T.EvaporadorMultiefecto("W4", "Venus T1500 (TVR)", 1000, 320, N=p["N"], T1=p["T1"], TN=p["TN"], Ts=p["Ts"], tvr=p["tvr"], Ra=p["Ra"], dT_tvr=p["dTtvr"],
                              etiquetas_condensados="F1a,F1b,F1c" if p["N"] == 3 else ",".join(f"F1_{i + 1}" for i in range(p["N"]))))
    E(T.Esterilizador("W5", "Esterilizador", 840, 320, T_salida=p["Tst"]))
    E(T.EnfriamientoFlash("B2", "Cámara de enfriamiento flash", 680, 320, T_final=p["Tcool"], flash=p["flash"]))
    E(T.LlenadoraAseptica("A1", "Llenadora aséptica", 520, 320))
    E(CalderaGas("D1", "Calderas a gas natural", 200, 290))
    C = pl.conectar
    C("B1", "producto", "F1", "entrada", nombre="1"); C("F1", "producto", "Z1", "entrada", nombre="2")
    C("Z1", "producto", "W1", "entrada", nombre="4"); C("W1", "producto", "F2", "entrada", nombre="5")
    C("F2", "jugo", "W2", "entrada", nombre="6"); C("W2", "concentrado", "W3", "entrada", nombre="8")
    C("W3", "concentrado", "W4", "entrada", nombre="10"); C("W4", "concentrado", "W5", "entrada", nombre="12")
    C("W5", "producto", "B2", "entrada", nombre="15"); C("B2", "producto", "A1", "entrada", nombre="16")
    C("D1", "vapor", "W1", "vapor", nombre="V1"); C("D1", "vapor", "W4", "vapor", nombre="V2"); C("D1", "vapor", "W5", "vapor", nombre="V3")
    pl.especs.append(EspecDiseno("W4", "brix_salida", "A1", "x", p["xP"], "°Brix de la pasta envasada"))
    pl.instrumentos += [
        Instrumento("TIC", "101", "W1", "dcs", "Temperatura de salida del hot break", "T_salida", "TV-101"),
        Instrumento("FIC", "201", "W2", "dcs", "Caudal de alimentación al Apollo", None, "FV-201"),
        Instrumento("PIC", "301", "W4", "dcs", "Vacío del último efecto del Venus", "TN", "PV-301"),
        Instrumento("DIC", "302", "W4", "dcs", "°Brix (densidad) a la salida del Venus", "brix_salida", "DV-302"),
        Instrumento("TIC", "401", "W5", "dcs", "Temperatura de esterilización", "T_salida", "TV-401"),
        Instrumento("PIC", "501", "B2", "dcs", "Vacío de la cámara flash", "T_final", "PV-501"),
    ]
    pl._p = p
    pl.resolver()
    if capacidades:                       # capacidad nominal de partida (PAT 132), como el simulador del profesor
        _cap.aplicar(pl)
    return pl


def resumen(pl: Planta, cop=2.0) -> dict:
    """Las cifras del Capítulo 1: demanda, mapa, cascada, pinch, alternativas y gas."""
    p = pl._p; snk = [s for s in pl.sumideros() if s.equipo == "W1"][0]
    m = rec.mapa(pl.residuales(), snk, p["dT"], p["Tfin"])
    casc, filas = rec.cascada(m); tg, qh, pin = rec.pinch(m)
    cond = rec.mapa(pl.residuales(), snk, p["dT"], p["Tfin"], incluir=[s[0] for s in m.corrientes if s[3] is not None])
    alt2, _ = rec.cascada(cond)
    frias = sorted([s for s in m.corrientes], key=lambda s: (0 if s[0] == "F3" else 1 if s[0] == "F2" else 2, s[1]))
    hp = rec.bomba_calor(snk.Q, cop, [s for s in m.corrientes if s[0] == "F3"] + [s for s in m.corrientes if s[0] == "F2"]
                         + [s for s in m.corrientes if s[0] == "F1c"])
    h = pl.equipos["B1"].horas(); cal = pl.equipos["D1"]
    W4 = pl.equipos["W4"].resultado.detalle
    out = dict(
        horas=h, M0=pl.salidas[("B1", "producto")].m, Qhb=snk.Q, CPc=snk.CP,
        P=pl.salidas[("A1", "producto")].m, xV=pl.equipos["W4"].v("brix_salida"),
        S_vivo=W4["S"], economia_venus=W4["economia"], T_venus=W4["T"],
        Wc_MVR=pl.servicio_total("electricidad_kW"),
        excedente_MVR=sum(e.resultado.detalle.get("excedente_kW", 0) for e in pl.equipos.values() if e.tipo == "evaporador_mvr"),
        corrientes={s[0]: s for s in m.corrientes}, oferta=m.oferta,
        cascada=casc, cascada_filas=filas, cobertura_cascada=casc / snk.Q,
        pinch=tg, cobertura_pinch=tg / snk.Q, Q_externo_min=qh, T_pinch=pin,
        alt2=alt2, cobertura_alt2=alt2 / snk.Q, bomba_calor=hp,
        vapor_linea_kW=cal.resultado.detalle["Q_vapor_kW"], gas_linea_kgh=cal.resultado.detalle["gas_kgh"],
        gas_base=eco.gas(snk.Q, h, cal), gas_cascada=eco.gas(casc, h, cal),
    )
    return out
