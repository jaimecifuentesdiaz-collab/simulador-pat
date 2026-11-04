"""Catálogo de equipos de biocombustibles sólidos de madera: pellet, chip de madera y leña (fase 6, 29-10-2026).

La biomasa se modela como una corriente de tipo «biomasa»: m es el caudal húmedo (kg/h) y s la materia seca (kg/h), de modo
que la humedad en base húmeda es 1 − s/m. El calor específico de la madera húmeda es la mezcla de la madera seca (cps) y
el agua: cp = x·cps + (1 − x)·4,18. Cada equipo declara su categoría de la Tabla C.1 y su letra del Anexo D de la ISO 10628.

Balances:
- Secador: materia seca constante (salida = entrada × (1 − M_entrada) / (1 − M_salida)), como en el simulador del profesor,
  más el balance de energía con referencia en agua líquida a 0 °C: el aire de secado entra a T_aire_entrada y sale a
  T_aire_salida con el agua evaporada. El calor para calentar ese aire desde el ambiente es la demanda del generador de
  calor y el sumidero del mapa de recuperación; el escape (aire caliente y húmedo) es el calor residual.
- Equipos mecánicos: la electricidad (energía específica por tonelada) se disipa en el producto (sube su temperatura) o al
  ambiente, según la fracción declarada.
- Enfriador de pellet: el calor que entregan los pellets calientes sale con el aire del enfriador (calor residual).
"""
from __future__ import annotations
from ..motor.equipos import Equipo, Puerto, Resultado, Sumidero, P, capacidad_param
from ..motor.corrientes import Corriente, Residual
from ..motor.propiedades import CPW, psat_kPa, tsat_C, latente

RUBROS_BIOMASA = ("pellet", "chip", "lena")
P_ATM = 101.325        # kPa
CPA = 1.006            # kJ/kg·K, aire seco a 0 °C (Engineering ToolBox, s. f., calor específico del aire)
CPV = 1.864            # kJ/kg·K, vapor de agua a 300 K (Engineering ToolBox, s. f., calor específico del vapor de agua)
H0 = latente(0.01)     # kJ/kg, calor de vaporización en el punto triple (IAPWS-IF97): 2.500,9
F_ISO18125 = 2.443     # MJ/kg por unidad de humedad base húmeda (ISO 18125:2017, poder calorífico inferior en base húmeda)

FUENTE_PSICRO = "Engineering ToolBox (s. f.): cp del aire seco 1,006 kJ/kg·K (0 °C) y del vapor 1,864 kJ/kg·K (300 K); IAPWS-IF97"
FUENTE_CP_MADERA = "Glass y Zelinka (2010), Wood Handbook, FPL-GTR-190, cap. 4, ec. 4-16a, pp. 4-10 y 4-11: cp0 = 0,1031 + 0,003867·T (K)"
FUENTE_PCI = "Alakangas et al. (2015, anexo 5, p. 49): valor típico de la ISO 17225-1, Tabla B.3 (residuo forestal de conífera)"
TO = "Thek y Obernberger (2009)"
FUENTE_ENPLUS = "European Pellet Council (2022), ENplus ST 1001:2022, anexo A.1, Tabla 4, p. 36"


def h_vapor(T: float) -> float:
    """Entalpía del vapor de agua en el aire a T (°C), kJ/kg, con referencia en agua líquida a 0 °C."""
    return H0 + CPV * T


def cp_madera_seca(T: float) -> float:
    """Calor específico de la madera anhidra (kJ/kg·K) a T (°C), Wood Handbook (Glass y Zelinka, 2010), cap. 4, ec. 4-16a."""
    return 0.1031 + 0.003867 * (T + 273.15)


def humedad_bh(c: Corriente) -> float:
    return 1 - c.s / c.m if c.m else 0.0


def humedad_bs(c: Corriente) -> float:
    return (c.m - c.s) / c.s if c.s else 0.0


def pci_humedo(pci_seco: float, M: float) -> float:
    """Poder calorífico inferior en base húmeda (MJ/kg), ISO 18125: q = q_seco·(1 − M) − 2,443·M, con M en fracción."""
    return pci_seco * (1 - M) - F_ISO18125 * M


def corriente_biomasa(nombre: str, m: float, M: float, T: float, cps: float, **extra) -> Corriente:
    return Corriente(nombre, "biomasa", m=m, s=m * (1 - M), T=T, fase="solido", cps=cps, extra=dict(extra))


class EquipoBiomasa(Equipo):
    rubro = "biomasa"; rubros = RUBROS_BIOMASA


# ----------------------------------------------------------------------------------------------- alimentación
class AlimentacionBiomasa(EquipoBiomasa):
    tipo = "alimentacion_biomasa"; nombre_tipo = "Recepción de biomasa (cancha y tolva)"
    iso_categoria = 1; iso_letra = "B"; simbolo = "tolva"
    entradas = []
    salidas = [Puerto("producto", "biomasa", "Biomasa verde")]
    params_base = [
        P("materia", "Materia prima", "Aserrín verde de pino radiata", "", "Usuario", "", "Solo descriptivo"),
        P("carga_t_h", "Biomasa verde que entra a la planta", 8.0, "t/h", "Usuario", "", "Se ajusta con la especificación de producción", 0.1, 200),
        P("humedad", "Humedad de la biomasa verde (base húmeda)", 0.55, "kg/kg", "Literatura", "Alakangas et al. (2015, p. 44): aserrín, clase M55",
          "Cada escenario fija la de su materia prima", 0.05, 0.70),
        P("T", "Temperatura de la biomasa (ambiente)", 15.0, "°C", "Supuesto", "", "Temperatura media anual cercana a la de la zona centro-sur de Chile", -5, 35),
        P("cps", "Calor específico de la madera seca", round(cp_madera_seca(15.0), 4), "kJ/kg·K", "Literatura", FUENTE_CP_MADERA, "Evaluado a la temperatura de la biomasa"),
        P("PCI_seco", "Poder calorífico inferior de la madera seca", 19.2, "MJ/kg", "Literatura", FUENTE_PCI,
          "Se usa el mismo valor para pino y eucalipto; Araújo et al. (2018) miden 19,0 MJ/kg de poder superior en E. globulus", 15, 22),
        P("dias", "Días de operación al año", 330, "d", "Supuesto", "", "", 1, 366),
        P("horas_dia", "Horas de operación por día", 24, "h/d", "Supuesto", "", "Tres turnos", 1, 24),
    ]

    def horas(self):
        return float(self.v("dias")) * float(self.v("horas_dia"))

    def calcular(self, ent):
        m = float(self.v("carga_t_h")) * 1000; M = float(self.v("humedad"))
        c = corriente_biomasa(str(self.v("materia")), m, M, float(self.v("T")), float(self.v("cps")), PCI_seco=float(self.v("PCI_seco")))
        r = Resultado(salidas={"producto": c})
        r.energia_in = [("Biomasa verde", c.H())]; r.energia_out = [("Biomasa verde", c.H())]
        r.detalle = dict(horas=self.horas(), carga_t_h=m / 1000, humedad_bh=M, humedad_bs=M / (1 - M) if M < 1 else None,
                         materia_seca_t_h=c.s / 1000)
        return r


# ----------------------------------------------------------------------------------------------- secado
class SecadorBiomasa(EquipoBiomasa):
    tipo = "secador_biomasa"; nombre_tipo = "Secador rotatorio de biomasa (tambor)"
    iso_categoria = 9; iso_letra = "T"; simbolo = "secador_tambor"
    entradas = [Puerto("entrada", "biomasa", "Biomasa húmeda"), Puerto("calor", "calor", "Aire caliente del generador")]
    salidas = [Puerto("producto", "biomasa", "Biomasa seca"), Puerto("escape", "aire", "Aire húmedo de escape")]
    params_base = [
        P("humedad_salida", "Humedad a la salida (base húmeda)", 0.10, "kg/kg", "Literatura", "Thek y Obernberger (2009), sec. 3.2: de 55 a 10 % antes de pelletizar", "", 0.03, 0.6),
        P("T_aire_entrada", "Temperatura del gas de secado a la entrada", 255.0, "°C", "Literatura", "Mani, Sokhansanj y Bi (2005, Tabla 1): secador rotatorio",
          "Smith (2023) indica 260 °C como mínimo y cerca de 400 °C como óptimo", 50, 600),
        P("T_aire_salida", "Temperatura del aire de escape", 90.0, "°C", "Supuesto", "",
          "Ninguna fuente abierta da la temperatura medida del escape; se varía en la sensibilidad", 35, 150),
        P("T_producto", "Temperatura de la biomasa seca a la salida", 60.0, "°C", "Supuesto", "", "Algo menor que la del escape", 20, 120),
        P("perdidas", "Pérdidas por la carcasa (fracción del calor útil)", 0.05, "—", "Supuesto", "", "", 0, 0.3),
        P("T_ambiente", "Temperatura del aire ambiente que se calienta", 15.0, "°C", "Supuesto", "", "", -5, 35),
        P("energia_especifica", "Electricidad de ventiladores y accionamiento", 20.0, "kWh/t", "Derivado",
          "Uasuf (2010, pp. 31 y 33): sistema de secado de 280 kW en una planta de 6 t/h de pellet, simultaneidad de 85 %",
          "280 kW × 0,85 / 12 t/h de aserrín al 55 % ≈ 20 kWh por tonelada que entra", 0, 100),
        P("T_condensacion", "Temperatura hasta la que se puede enfriar el escape", 30.0, "°C", "Supuesto",
          "Igual a la temperatura final de los residuales del Capítulo 1", "", 10, 60),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Mo = float(self.v("humedad_salida"))
        Tae, Tas, Tp = float(self.v("T_aire_entrada")), float(self.v("T_aire_salida")), float(self.v("T_producto"))
        Tamb, perd = float(self.v("T_ambiente")), float(self.v("perdidas"))
        r = Resultado()
        Mi = humedad_bh(e)
        if Mo >= Mi:
            r.avisos.append(f"{self.id}: la humedad de salida ({Mo:.0%}) no es menor que la de entrada ({Mi:.0%}); el secador no evapora")
            Mo = Mi
        m_out = e.s / (1 - Mo) if Mo < 1 else e.m
        E = max(e.m - m_out, 0.0)                                    # agua evaporada, kg/h
        p = e.fraccion(1.0); p.m = m_out; p.T = Tp; p.nombre = "Biomasa seca"
        Hv = E * h_vapor(Tas) / 3600
        Q_util = p.H() + Hv - e.H()                                  # kW
        Q_perd = Q_util * perd / (1 - perd) if perd < 1 else 0.0
        Q_sec = Q_util + Q_perd
        if Tae <= Tas:
            raise ValueError(f"{self.id}: la temperatura del aire de entrada debe ser mayor que la del escape")
        m_aire = Q_sec * 3600 / (CPA * (Tae - Tas))                  # kg/h de aire seco
        Q_aire = m_aire * CPA * (Tae - Tamb) / 3600                  # calor para llevar el aire del ambiente a Tae
        W = float(self.v("energia_especifica")) * e.m / 1000
        H_esc = m_aire * CPA * Tas / 3600 + Hv
        esc = Corriente("Escape del secador", "aire", m=m_aire + E, s=0.0, T=Tas, fase="gas",
                        cp=H_esc * 3600 / ((m_aire + E) * Tas) if Tas else CPA, extra=dict(aire_kgh=m_aire, agua_kgh=E))
        r.salidas = {"producto": p, "escape": esc}
        r.servicios = dict(calor_kW=Q_aire, electricidad_kW=W, aire_kgh=m_aire)
        r.sumideros = [Sumidero("Aire de secado", self.id, Tamb, Tae, m_aire * CPA / 3600)]
        # escape: sensible hasta el punto de rocío y condensación lineal hasta T_condensacion
        Tc = float(self.v("T_condensacion"))
        Y = E / m_aire if m_aire else 0.0
        Pv = P_ATM * Y / (0.622 + Y)
        Td = tsat_C(Pv) if Pv > 0 else -50.0
        CPs = (m_aire * CPA + E * CPV) / 3600
        res = []
        if Td > Tc:
            Td = min(Td, Tas)
            if Tas > Td:
                res.append(Residual(f"Escape sensible {self.id}", self.id, Tas, CPs, CPs * (Tas - Td), Td, "Aire húmedo de escape hasta el punto de rocío"))
            ps = psat_kPa(Tc); Ys = 0.622 * ps / (P_ATM - ps)
            Ec = max(E - m_aire * Ys, 0.0)
            Q2 = Ec * latente((Td + Tc) / 2) / 3600 + CPs * (Td - Tc)
            res.append(Residual(f"Escape latente {self.id}", self.id, Td, Q2 / (Td - Tc), Q2, Tc,
                                "Condensación del vapor del escape entre el punto de rocío y la temperatura de condensación"))
        elif Tas > Tc:
            res.append(Residual(f"Escape sensible {self.id}", self.id, Tas, CPs, CPs * (Tas - Tc), Tc, "Aire húmedo de escape (no alcanza el punto de rocío)"))
        r.residuales = res
        r.energia_in = [("Biomasa húmeda", e.H()), ("Aire de secado (a la entrada)", m_aire * CPA * Tae / 3600), ("Electricidad", W)]
        r.energia_out = [("Biomasa seca", p.H()), ("Escape: aire", m_aire * CPA * Tas / 3600), ("Escape: vapor de agua", Hv),
                         ("Pérdidas por la carcasa", Q_perd), ("Electricidad disipada", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, humedad_entrada=Mi, humedad_salida=Mo, agua_evaporada_kgh=E, aire_kgh=m_aire,
                         Q_util_kW=Q_util, Q_aire_kW=Q_aire, consumo_MJ_kg_agua=Q_aire * 3.6 / E if E else None,
                         T_rocio=Td, W_kW=W)
        return r


def _variante(base, **valores):
    """Copia de una lista de parámetros con otros valores por defecto: _variante(lista, clave=dict(valor=…, fuente=…))."""
    return [P(**{**p.a_dict(), **valores[p.clave]}) if p.clave in valores else p for p in base]


class SecadorBanda(SecadorBiomasa):
    tipo = "secador_banda"; nombre_tipo = "Secador de banda a baja temperatura"; simbolo = "secador_banda"
    params_base = _variante(
        SecadorBiomasa.params_base,
        T_aire_entrada=dict(valor=90.0, fuente=f"{TO}, sec. 3.2: secador de banda con agua caliente a 90 °C",
                            justificacion="Müller, Strauch y Schade (2024) usan 120 °C"),
        T_aire_salida=dict(valor=45.0, categoria="Supuesto", fuente="", justificacion="Secado a baja temperatura; se varía en la sensibilidad"),
        T_producto=dict(valor=40.0), humedad_salida=dict(valor=0.25, categoria="Oficial", fuente="ISO 17225-4, clase M25 (Natural Resources Canada, s. f., Tabla 1)"),
        energia_especifica=dict(valor=10.0, fuente="Müller, Strauch y Schade (2024), lámina 6: cerca de 25 kWh por t de agua",
                                justificacion="25 kWh/t de agua × ~0,4 t de agua por t que entra"))


class SecadorLena(SecadorBiomasa):
    tipo = "secador_lena"; nombre_tipo = "Secador de leña (cámara o contenedor)"; simbolo = "secador"
    params_base = _variante(
        SecadorBiomasa.params_base,
        T_aire_entrada=dict(valor=80.0, fuente="Wengert (2008): hornos de leña de roble a 60, 82 y 104 °C (datos del FPL)",
                            justificacion="Valor intermedio del rango", minimo=40, maximo=120),
        T_aire_salida=dict(valor=50.0, categoria="Supuesto", fuente=""), T_producto=dict(valor=45.0),
        humedad_salida=dict(valor=0.18, categoria="Oficial", fuente="NCh2907, Tabla 1 (DS 47/2015 MMA, art. 3): leña seca bajo 25 % en base seca",
                            justificacion="18 % en base húmeda = 22 % en base seca, con margen bajo el límite"),
        perdidas=dict(valor=0.15, justificacion="Mayor que en los secadores continuos; de Kofman (2013, p. 3) se deriva cerca de 12 MJ de calor por kg de agua en hornos de leña (8,04 GJ por t de leña de 45 a 15 %, caldera de 80 %)"))


# ----------------------------------------------------------------------------------------------- equipos mecánicos
class EquipoMecanico(EquipoBiomasa):
    """Electricidad = energía específica × carga; la fracción_calor de esa energía calienta el producto y el resto se pierde."""
    entradas = [Puerto("entrada", "biomasa")]
    salidas = [Puerto("producto", "biomasa")]
    nombre_producto = "Producto"

    def calcular(self, ent):
        e = ent["entrada"]; W = float(self.v("energia_especifica")) * e.m / 1000; f = float(self.v("fraccion_calor"))
        p = e.fraccion(1.0); p.nombre = self.nombre_producto
        CP = p.CP(); p.T = e.T + (W * f / CP if CP else 0.0)
        r = Resultado(salidas={"producto": p}); r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Biomasa", e.H()), ("Electricidad", W)]
        r.energia_out = [(self.nombre_producto, p.H()), ("Electricidad perdida al ambiente", W * (1 - f))]
        r.detalle = dict(carga_t_h=e.m / 1000, W_kW=W, T_salida=p.T)
        return r


def _mec(energia, fuente, cat="Literatura", fraccion=1.0, just="Por tonelada de biomasa que entra"):
    return [P("energia_especifica", "Energía eléctrica específica", energia, "kWh/t", cat, fuente, just, 0, 300),
            P("fraccion_calor", "Fracción de la electricidad que calienta el producto", fraccion, "—", "Supuesto", "",
              "El resto se pierde al ambiente por el motor y la carcasa", 0, 1),
            capacidad_param()]


class Astilladora(EquipoMecanico):
    tipo = "astilladora"; nombre_tipo = "Astilladora de disco"; simbolo = "astilladora"; iso_categoria = 10; iso_letra = "Z"
    rubros = ("chip",); nombre_producto = "Astilla verde"
    params_base = _mec(3.33, "Di Fulvio et al. (2015, Tabla 2): astilladora de disco eléctrica de 30 kW con pino, por tonelada fresca", fraccion=0.5)


class MolinoMartillos(EquipoMecanico):
    tipo = "molino_martillos"; nombre_tipo = "Molino de martillos"; simbolo = "molino_martillos"; iso_categoria = 10; iso_letra = "Z"
    rubros = ("pellet",); nombre_producto = "Aserrín molido"
    params_base = _mec(30.0, "Naehrig (s. f.), KAHL: molino de martillos 25 a 35 kWh por tonelada de pellet", "Fabricante", fraccion=0.5,
                       just="Punto medio; por tonelada que entra (casi igual a la de pellet)")


class Pelletizadora(EquipoBiomasa):
    tipo = "pelletizadora"; nombre_tipo = "Pelletizadora de matriz anular"; simbolo = "pelletizadora"; iso_categoria = 13; iso_letra = "A"
    rubros = ("pellet",)
    entradas = [Puerto("entrada", "biomasa", "Aserrín molido")]
    salidas = [Puerto("producto", "biomasa", "Pellet caliente")]
    params_base = [
        P("energia_especifica", "Energía eléctrica específica de la prensa", 52.5, "kWh/t", "Fabricante",
          "Naehrig (s. f.), KAHL: matriz anular 50 a 55 kWh/t sin vapor (40 a 45 con vapor)", "Punto medio, por tonelada que entra", 0, 300),
        P("T_salida", "Temperatura del pellet a la salida de la prensa", 90.0, "°C", "Literatura",
          "Ståhl y Berghel (2025): 70 a 90 °C; Uasuf (2010, p. 10): 90 a 95 °C", "", 40, 130),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; W = float(self.v("energia_especifica")) * e.m / 1000
        p = e.fraccion(1.0); p.nombre = "Pellet caliente"; CP = p.CP()
        Ts = float(self.v("T_salida")); Q = CP * (Ts - e.T)
        r = Resultado()
        if Q > W:
            r.avisos.append(f"{self.id}: la electricidad de la prensa ({W:,.0f} kW) no alcanza para llevar el pellet a {Ts:.0f} °C; "
                            "se calcula la temperatura con toda la electricidad (falta acondicionamiento con vapor)")
            Ts = e.T + W / CP if CP else e.T; Q = W
        p.T = Ts
        r.salidas = {"producto": p}; r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Aserrín molido", e.H()), ("Electricidad", W)]
        r.energia_out = [("Pellet caliente", p.H()), ("Electricidad perdida al ambiente", W - Q)]
        r.detalle = dict(carga_t_h=e.m / 1000, W_kW=W, T_salida=Ts, calor_al_pellet_kW=Q)
        return r


class EnfriadorPellet(EquipoBiomasa):
    tipo = "enfriador_pellet"; nombre_tipo = "Enfriador de pellet en contracorriente"; simbolo = "enfriador_contracorriente"
    iso_categoria = 9; iso_letra = "T"; rubros = ("pellet",)
    entradas = [Puerto("entrada", "biomasa", "Pellet caliente"), Puerto("aire", "aire", "Aire ambiente")]
    salidas = [Puerto("producto", "biomasa", "Pellet frío")]
    params_base = [
        P("T_ambiente", "Temperatura del aire ambiente", 15.0, "°C", "Supuesto", "", "", -5, 35),
        P("dT_pellet", "Pellet frío sobre la temperatura ambiente", 5.0, "K", "Literatura", "Ståhl y Berghel (2025): ambiente + 5 °C", "", 0, 30),
        P("T_aire_salida", "Temperatura del aire que sale del enfriador", 60.0, "°C", "Derivado",
          "Ståhl y Berghel (2025): cerca de 2 m³ de aire por kg de pellet",
          "1,6 kJ/kg·K × (90 − 20) K / (2,4 kg de aire × 1,006) ≈ 46 K sobre el ambiente", 20, 110),
        P("energia_especifica", "Electricidad del ventilador", 5.0, "kWh/t", "Literatura", "Risović, Đukić y Vučković (2008, p. 99): cerca de 5 kWh/t", "Por tonelada que entra", 0, 50),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Ta = float(self.v("T_ambiente")); W = float(self.v("energia_especifica")) * e.m / 1000
        p = e.fraccion(1.0); p.nombre = "Pellet frío"; p.T = min(e.T, Ta + float(self.v("dT_pellet")))
        Q = e.H() - p.H(); Tas = min(float(self.v("T_aire_salida")), e.T)
        r = Resultado(salidas={"producto": p}); r.servicios = dict(electricidad_kW=W)
        if Q > 0 and Tas > Ta:
            CPair = Q / (Tas - Ta)
            r.residuales = [Residual(f"Aire del enfriador {self.id}", self.id, Tas, CPair, Q, None, "Aire caliente del enfriador de pellet")]
            r.detalle["aire_kgh"] = CPair * 3600 / CPA
        r.energia_in = [("Pellet caliente", e.H()), ("Electricidad", W)]
        r.energia_out = [("Pellet frío", p.H()), ("Calor al aire del enfriador", Q), ("Electricidad disipada", W)]
        r.detalle.update(carga_t_h=e.m / 1000, Q_kW=Q, W_kW=W, T_pellet=p.T)
        return r


class CribaBiomasa(EquipoBiomasa):
    tipo = "criba_biomasa"; nombre_tipo = "Criba (harnero) de biomasa"; simbolo = "criba"; iso_categoria = 6; iso_letra = "F"
    entradas = [Puerto("entrada", "biomasa")]
    salidas = [Puerto("producto", "biomasa", "Producto aceptado"), Puerto("rechazo", "subproducto", "Finos y sobretamaño")]
    params_base = [
        P("rechazo", "Fracción rechazada (finos y sobretamaño)", 0.03, "kg/kg", "Literatura",
          "Sultana, Kumar y Harfield (2010, sec. 2): finos sobre 3 % indican un problema; Pirraglia et al. (2010, p. 2377) recirculan 10 %",
          "El rechazo sale como subproducto; la recirculación no se modela", 0, 0.5),
        P("energia_especifica", "Electricidad de la criba", 1.0, "kWh/t", "Supuesto", "", "Por tonelada que entra", 0, 20),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; f = float(self.v("rechazo")); W = float(self.v("energia_especifica")) * e.m / 1000
        p = e.fraccion(1 - f); p.nombre = "Producto aceptado"
        d = e.fraccion(f); d.nombre = "Rechazo de la criba"; d.tipo = "subproducto"
        r = Resultado(salidas={"producto": p, "rechazo": d}); r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Biomasa", e.H()), ("Electricidad", W)]
        r.energia_out = [("Producto aceptado", p.H()), ("Rechazo", d.H()), ("Electricidad disipada", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, W_kW=W, rechazo_t_h=d.m / 1000)
        return r


class SierraLena(EquipoBiomasa):
    tipo = "sierra_lena"; nombre_tipo = "Sierra de trozado y partidora (procesadora de leña)"; simbolo = "sierra"
    iso_categoria = 13; iso_letra = "A"; rubros = ("lena",)
    entradas = [Puerto("entrada", "biomasa", "Trozas")]
    salidas = [Puerto("producto", "biomasa", "Leña trozada y partida"), Puerto("aserrin", "subproducto", "Aserrín del corte")]
    params_base = [
        P("energia_especifica", "Energía eléctrica específica", 20.0, "kWh/t", "Derivado",
          "Procesadora Hakki Pilke 43 Pro de 15 kW (Agriculture-XPRT, s. f.) y 0,70 m³ sólidos por hora de una procesadora (Forestry Commission, 2003, Tabla 2)",
          "15 kW / (0,70 m³/h × 1.070 kg/m³ de eucalipto verde, supuesto) ≈ 20 kWh/t", 0, 100),
        P("aserrin", "Aserrín del corte sobre la madera que entra", 0.01, "kg/kg", "Supuesto", "", "Corte de la cadena; sin medición", 0, 0.1),
        P("fraccion_calor", "Fracción de la electricidad que calienta la leña", 0.2, "—", "Supuesto", "", "", 0, 1),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; W = float(self.v("energia_especifica")) * e.m / 1000; f = float(self.v("fraccion_calor"))
        a = float(self.v("aserrin"))
        p = e.fraccion(1 - a); p.nombre = "Leña trozada y partida"
        d = e.fraccion(a); d.nombre = "Aserrín"; d.tipo = "subproducto"
        CP = e.CP(); dT = W * f / CP if CP else 0.0; p.T = d.T = e.T + dT
        r = Resultado(salidas={"producto": p, "aserrin": d}); r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Trozas", e.H()), ("Electricidad", W)]
        r.energia_out = [("Leña", p.H()), ("Aserrín", d.H()), ("Electricidad perdida al ambiente", W * (1 - f))]
        r.detalle = dict(carga_t_h=e.m / 1000, W_kW=W)
        return r


# ----------------------------------------------------------------------------------------------- producto
class DespachoBiomasa(EquipoBiomasa):
    """Ensacado o acopio del producto: verifica la humedad y el poder calorífico contra la norma elegida."""
    tipo = "despacho_biomasa"; nombre_tipo = "Ensacado o acopio del producto"; simbolo = "maquina_acabado"; iso_categoria = 13; iso_letra = "A"
    entradas = [Puerto("entrada", "biomasa")]
    salidas = [Puerto("producto", "biomasa", "Producto despachado")]
    params_base = [
        P("norma", "Norma de calidad", "ENplus A1 (ISO 17225-2)", "", "Oficial", FUENTE_ENPLUS, ""),
        P("humedad_max", "Humedad máxima que admite la norma", 0.10, "kg/kg", "Oficial", FUENTE_ENPLUS, "", 0, 1),
        P("base_humedad", "Base de la humedad de la norma (bh o bs)", "bh", "", "Oficial", FUENTE_ENPLUS, "bh: base húmeda; bs: base seca"),
        P("PCI_min", "Poder calorífico inferior mínimo (base húmeda)", 16.5, "MJ/kg", "Oficial", FUENTE_ENPLUS + ": 4,6 kWh/kg",
          "0 si la norma no lo fija", 0, 25),
        P("PCI_seco", "Poder calorífico inferior de la madera seca (si no viene en la corriente)", 19.2, "MJ/kg", "Literatura", FUENTE_PCI, "", 15, 22),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; M = humedad_bh(e); Mbs = humedad_bs(e)
        pci_s = float(e.extra.get("PCI_seco", self.v("PCI_seco"))); pci = pci_humedo(pci_s, M)
        Mlim = float(self.v("humedad_max")); base = str(self.v("base_humedad"))
        ok_h = (Mbs if base == "bs" else M) <= Mlim + 1e-12; ok_p = pci >= float(self.v("PCI_min")) - 1e-12
        r = Resultado()
        if not ok_h:
            r.avisos.append(f"{self.id}: la humedad del producto ({(Mbs if base == 'bs' else M):.1%} {base}) supera el máximo de {self.v('norma')} ({Mlim:.0%})")
        if not ok_p:
            r.avisos.append(f"{self.id}: el poder calorífico ({pci:.2f} MJ/kg) es menor que el mínimo de {self.v('norma')}")
        p = e.fraccion(1.0); p.nombre = "Producto despachado"; r.salidas = {"producto": p}
        r.energia_in = [("Producto", e.H())]; r.energia_out = [("Producto despachado", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000, producto_t_h=e.m / 1000, humedad_bh=M, humedad_bs=Mbs, PCI_MJ_kg=pci,
                         cumple_humedad=ok_h, cumple_pci=ok_p, T=e.T)
        return r


# ----------------------------------------------------------------------------------------------- servicio térmico
class GeneradorCalorBiomasa(EquipoBiomasa):
    """Hogar o generador de aire caliente que quema biomasa (corteza, aserrín o despuntes) para el secador.
    Su carga es la suma de la demanda de calor de los secadores conectados a su puerto «calor»."""
    tipo = "caldera_biomasa"; nombre_tipo = "Generador de calor a biomasa (hogar)"; simbolo = "horno"; iso_categoria = 4; iso_letra = "D"
    combustible = "biomasa"
    entradas = [Puerto("aire", "aire", "Aire de combustión")]
    salidas = [Puerto("calor", "calor", "Aire caliente al secador"), Puerto("humos", "humos", "Humos a la chimenea")]
    params_base = [
        P("combustible_nombre", "Combustible", "Astilla de pino con corteza", "", "Usuario", "", "Solo descriptivo"),
        P("PCI_seco", "Poder calorífico inferior del combustible seco", 19.2, "MJ/kg", "Literatura", FUENTE_PCI, "", 10, 22),
        P("humedad_combustible", "Humedad del combustible (base húmeda)", 0.55, "kg/kg", "Literatura",
          "Alakangas et al. (2015, pp. 43-44): residuo forestal M55 y corteza M55+", "", 0, 0.65),
        P("eta", "Rendimiento del generador sobre el poder calorífico inferior", 0.80, "—", "Literatura",
          "Sultana, Kumar y Harfield (2010, sec. 5.3.4.2): caldera de 80 %", "Uasuf (2010, p. 32) usa 10 % de pérdida de conversión", 0.4, 0.95),
        P("C_seco", "Carbono de la madera seca", 0.498, "kg/kg", "Literatura", "Beets y Garrett (2018, Tabla 1, p. 3): fuste de pino radiata",
          "Para el CO2 biogénico", 0.4, 0.6),
        P("densidad", "Densidad a granel del combustible (por m³ estéreo)", 300.0, "kg/m³", "Derivado",
          "Alakangas et al. (2015, pp. 43-44): 250 la astilla de fuste y 350 la corteza", "Valor intermedio para astilla con corteza; convierte toneladas en m³ estéreo para el precio de INFOR", 100, 800),
    ]

    @property
    def pci_ar(self) -> float:
        return pci_humedo(float(self.v("PCI_seco")), float(self.v("humedad_combustible")))

    def consumo(self, Q_kW: float, horas: float) -> dict:
        """Combustible que quema el generador para entregar Q_kW durante 'horas'."""
        fuel_kWh = Q_kW * horas / float(self.v("eta")); kg = fuel_kWh * 3.6 / self.pci_ar
        kg_s = kg * (1 - float(self.v("humedad_combustible")))
        return dict(MWh_pci=fuel_kWh / 1000, t=kg / 1000, t_seca=kg_s / 1000, m3=kg / float(self.v("densidad")),
                    co2_biogenico_t=kg_s * float(self.v("C_seco")) * 44 / 12 / 1000)

    def calcular(self, ent):
        Q = float(ent.get("_demanda_kW", 0.0)); fuel = Q / float(self.v("eta")); kg = fuel * 3.6 / self.pci_ar
        r = Resultado(salidas={"calor": Corriente("Aire caliente", "calor", m=0.0, fase="gas", extra=dict(Q_kW=Q))})
        r.energia_in = [("Biomasa combustible (poder calorífico inferior)", fuel)]
        r.energia_out = [("Calor entregado al aire de secado", Q), ("Pérdidas y humos", fuel - Q)]
        kg_s = kg * (1 - float(self.v("humedad_combustible")))
        r.detalle = dict(Q_calor_kW=Q, combustible_kW_pci=fuel, combustible_kgh=kg, combustible_seco_kgh=kg_s,
                         co2_biogenico_kgh=kg_s * float(self.v("C_seco")) * 44 / 12, PCI_humedo=self.pci_ar,
                         masa_entra=kg, masa_sale=kg)
        return r


CATALOGO = [AlimentacionBiomasa, SecadorBiomasa, SecadorBanda, SecadorLena, Astilladora, MolinoMartillos, Pelletizadora,
            EnfriadorPellet, CribaBiomasa, SierraLena, DespachoBiomasa, GeneradorCalorBiomasa]
