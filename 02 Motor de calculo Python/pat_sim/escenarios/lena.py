"""Escenario: planta de leña seca de eucalipto (rubro leña).

Línea: recepción de trozas, procesadora (sierra de trozado y partidora), secador de leña (cámara) y acopio con el
límite chileno de leña seca (25 % de humedad en base seca). Un generador de calor que quema despuntes calienta el aire."""
from __future__ import annotations
from ..motor.planta import Instrumento
from ..catalogos import biomasa as B
from .biomasa_comun import nueva_planta, fijar_produccion
from . import capacidades as _cap

NOMBRE = "Planta de leña seca (escenario base)"
BASE = dict(produccion=2.0, M0=0.53, Mseco=0.18, Tae=80.0, Tas=50.0, dias=300, hpd=24, Tfin=30.0, dT=5.0)
PARAMS = [
    ("produccion", "Leña seca producida (t/h)", 0.2, 20.0, 0.1, "%.1f"),
    ("M0", "Humedad de la leña verde (base húmeda)", 0.20, 0.65, 0.01, "%.2f"),
    ("Mseco", "Humedad de la leña seca (base húmeda)", 0.10, 0.30, 0.01, "%.2f"),
    ("Tae", "Temperatura del aire de secado (°C)", 40.0, 120.0, 5.0, "%.0f"),
    ("Tas", "Temperatura del escape del secador (°C)", 30.0, 80.0, 1.0, "%.0f"),
    ("dias", "Días de operación al año", 100, 366, 1, "%d"),
    ("dT", "Aproximación mínima de temperatura (°C)", 2.0, 15.0, 0.5, "%.1f"),
    ("Tfin", "Temperatura final de los residuales (°C)", 20.0, 40.0, 1.0, "%.1f"),
]


def crear(capacidades=True, **kw):
    p = dict(BASE); p.update(kw)
    pl = nueva_planta(NOMBRE, "lena", p); E = pl.agregar
    # E. nitens verde del Biobío: 101 a 129 % en base seca (Omonte et al., 2019), cerca de 115 % = 53 % en base húmeda
    E(B.AlimentacionBiomasa("B1", "Recepción de trozas", 40, 120, materia="Trozas verdes de eucalipto", humedad=p["M0"],
                            dias=p["dias"], horas_dia=p["hpd"]))
    E(B.SierraLena("A1", "Procesadora de leña", 200, 120))
    E(B.SecadorLena("T1", "Secador de leña", 360, 120, humedad_salida=p["Mseco"], T_aire_entrada=p["Tae"], T_aire_salida=p["Tas"],
                    T_condensacion=p["Tfin"]))
    # leña seca: humedad menor que 25 % en base seca, NCh2907 Tabla 1 (DS 47/2015 MMA, art. 3; SMA, 2018)
    E(B.DespachoBiomasa("A2", "Acopio de leña seca", 520, 120, norma="Leña seca, NCh2907 (menos de 25 % en base seca)", humedad_max=0.25,
                        base_humedad="bs", PCI_min=0.0))
    pl.equipos["A2"].set("humedad_max", 0.25, fuente="Superintendencia del Medio Ambiente (2018): NCh2907, Tabla 1, leña seca con humedad menor que 25 % en base seca")   # PAT 131
    pl.equipos["A2"].set("norma", "Leña seca, NCh2907 (menos de 25 % en base seca)", fuente="Superintendencia del Medio Ambiente (2018): NCh2907")
    E(B.GeneradorCalorBiomasa("D1", "Generador de calor a despuntes", 360, 290, combustible_nombre="Despuntes y aserrín de eucalipto"))
    C = pl.conectar
    C("B1", "producto", "A1", "entrada", nombre="1"); C("A1", "producto", "T1", "entrada", nombre="2")
    C("T1", "producto", "A2", "entrada", nombre="3"); C("D1", "calor", "T1", "calor", nombre="Q1")
    fijar_produccion(pl, "B1", "A2", p["produccion"], "Leña seca producida")
    pl.instrumentos += [
        Instrumento("TIC", "101", "T1", "plc", "Temperatura del aire de secado", "T_aire_entrada", "TV-101"),
        Instrumento("MI", "102", "T1", "campo", "Humedad de la leña (xilohigrómetro)", "humedad_salida", None),
    ]
    pl._p = p
    pl.resolver()
    if capacidades:                       # capacidad nominal de partida (PAT 132), como el simulador del profesor
        _cap.aplicar(pl)
    return pl
