"""Escenario: planta de pellet de madera a partir de aserrín verde de pino radiata (rubro pellet).

Línea: recepción, secador rotatorio, molino de martillos, pelletizadora de matriz anular, enfriador en contracorriente,
criba de finos y ensacado con la ISO 17225-2 (clase A1). Un generador de calor que quema corteza calienta el aire del secador.
Los valores por defecto y sus fuentes están en catalogos/biomasa.py; aquí van solo los que cambian para esta planta.
Tamaño: 5 t/h de pellet, la planta tipo de Thek y Obernberger (2009, Tabla I), que consume 113,9 kWh de electricidad por tonelada."""
from __future__ import annotations
from ..motor.planta import Instrumento
from ..catalogos import biomasa as B
from .biomasa_comun import nueva_planta, fijar_produccion
from . import capacidades as _cap

NOMBRE = "Planta de pellet de madera (escenario base)"
BASE = dict(produccion=5.0, M0=0.55, Mseco=0.10, Tae=255.0, Tas=90.0, dias=330, hpd=24, finos=0.03, Tfin=30.0, dT=5.0)
PARAMS = [  # (clave, etiqueta, mínimo, máximo, paso, formato) para la pestaña Escenario
    ("produccion", "Pellet producido (t/h)", 0.5, 30.0, 0.5, "%.1f"),
    ("M0", "Humedad del aserrín verde (base húmeda)", 0.20, 0.65, 0.01, "%.2f"),
    ("Mseco", "Humedad a la salida del secador (base húmeda)", 0.06, 0.15, 0.01, "%.2f"),
    ("Tae", "Temperatura del aire de secado (°C)", 80.0, 500.0, 10.0, "%.0f"),
    ("Tas", "Temperatura del escape del secador (°C)", 40.0, 130.0, 5.0, "%.0f"),
    ("dias", "Días de operación al año", 100, 366, 1, "%d"),
    ("finos", "Finos rechazados en la criba (fracción)", 0.0, 0.10, 0.005, "%.3f"),
    ("dT", "Aproximación mínima de temperatura (°C)", 2.0, 15.0, 0.5, "%.1f"),
    ("Tfin", "Temperatura final de los residuales (°C)", 20.0, 40.0, 1.0, "%.1f"),
]


def crear(capacidades=True, **kw):
    p = dict(BASE); p.update(kw)
    pl = nueva_planta(NOMBRE, "pellet", p); E = pl.agregar
    E(B.AlimentacionBiomasa("B1", "Recepción de aserrín verde", 40, 120, materia="Aserrín verde de pino radiata", humedad=p["M0"],
                            dias=p["dias"], horas_dia=p["hpd"]))
    E(B.SecadorBiomasa("T1", "Secador rotatorio", 200, 120, humedad_salida=p["Mseco"], T_aire_entrada=p["Tae"], T_aire_salida=p["Tas"],
                       T_condensacion=p["Tfin"]))
    E(B.MolinoMartillos("Z1", "Molino de martillos", 360, 120))
    E(B.Pelletizadora("A1", "Pelletizadora", 520, 120))
    E(B.EnfriadorPellet("T2", "Enfriador de pellet", 680, 120))
    E(B.CribaBiomasa("F1", "Criba de finos", 840, 120, rechazo=p["finos"]))
    E(B.DespachoBiomasa("A2", "Ensacado (ISO 17225-2 A1)", 1000, 120))
    E(B.GeneradorCalorBiomasa("D1", "Generador de calor a corteza", 200, 290))
    C = pl.conectar
    C("B1", "producto", "T1", "entrada", nombre="1"); C("T1", "producto", "Z1", "entrada", nombre="2")
    C("Z1", "producto", "A1", "entrada", nombre="3"); C("A1", "producto", "T2", "entrada", nombre="4")
    C("T2", "producto", "F1", "entrada", nombre="5"); C("F1", "producto", "A2", "entrada", nombre="6")
    C("D1", "calor", "T1", "calor", nombre="Q1")
    fijar_produccion(pl, "B1", "A2", p["produccion"], "Pellet producido")
    pl.instrumentos += [
        Instrumento("TIC", "101", "T1", "plc", "Temperatura del aire de secado a la entrada", "T_aire_entrada", "TV-101"),
        Instrumento("MIC", "102", "T1", "plc", "Humedad del aserrín a la salida del secador", "humedad_salida", "Velocidad del alimentador"),
        Instrumento("TI", "201", "A1", "plc", "Temperatura del pellet a la salida de la prensa", "T_salida", None),
        Instrumento("WIC", "301", "A2", "plc", "Peso del producto ensacado", None, None),
    ]
    pl._p = p
    pl.resolver()
    if capacidades:                       # capacidad nominal de partida (PAT 132), como el simulador del profesor
        _cap.aplicar(pl)
    return pl
