"""Equipos de servicios: caldera a gas natural (balance de combustión con datos de Engineering ToolBox)."""
from __future__ import annotations
from ..motor.equipos import Equipo, Puerto, Resultado, P
from ..motor.corrientes import Corriente


class CalderaGas(Equipo):
    """Generador de vapor a gas natural (metano). Su carga es la suma de la demanda de vapor de los equipos
    conectados a su puerto de vapor. Combustible en base de poder calorífico superior, como en fuel.py."""
    tipo = "caldera_gas"; nombre_tipo = "Caldera a gas natural"; rubro = "general"
    iso_categoria = 4; iso_letra = "D"; simbolo = "caldera"
    entradas = [Puerto("gas", "gas"), Puerto("aire", "aire"), Puerto("condensado", "condensado")]
    salidas = [Puerto("vapor", "vapor"), Puerto("humos", "humos")]
    params_base = [
        P("HHV", "Poder calorífico superior del gas", 55.5, "MJ/kg", "Literatura", "Engineering ToolBox (2003), metano"),
        P("LHV", "Poder calorífico inferior del gas", 50.0, "MJ/kg", "Literatura", "Engineering ToolBox (2003), metano"),
        P("eta_pci", "Rendimiento de la caldera sobre el poder calorífico inferior", 0.85, "—", "Supuesto", "Valor de referencia", "", 0.6, 0.98),
        P("densidad", "Densidad del gas", 0.67, "kg/m³", "Agrozzi", "Densidad declarada en el Anexo 10 de la DIA (metano a temperatura ambiente)"),
        P("co2_kg_kg", "CO2 por kg de gas", 2.75, "kg/kg", "Literatura", "Engineering ToolBox (2003), combustión del metano"),
        P("exceso_aire", "Exceso de aire", 0.10, "—", "Literatura", "Engineering ToolBox (2003): 5 a 10 % para gas natural", "", 0, 0.5),
    ]

    @property
    def eta_pcs(self) -> float:
        return float(self.v("eta_pci")) * float(self.v("LHV")) / float(self.v("HHV"))

    def calcular(self, ent):
        Q = float(ent.get("_demanda_vapor_kW", 0.0))
        fuel_kW = Q / self.eta_pcs                    # en base de poder calorífico superior
        kg = fuel_kW * 3.6 / float(self.v("HHV"))     # kg/h
        air_st = 4.0 / 0.232                          # kg de aire estequiométrico por kg de CH4 (O2 23,2 % en masa)
        exc = float(self.v("exceso_aire")); air = kg * air_st * (1 + exc)
        humos = Corriente("Humos", "humos", m=kg + air, T=0.0, fase="vapor",
                          extra=dict(CO2=kg * 2.75, H2O=kg * 2.25, O2=kg * 4 * exc, N2=air * 0.768))
        r = Resultado(salidas={"vapor": Corriente("Vapor", "vapor", m=0.0, fase="vapor", extra=dict(Q_kW=Q)), "humos": humos})
        r.energia_in = [("Gas natural (poder calorífico superior)", fuel_kW)]
        r.energia_out = [("Calor entregado al vapor", Q), ("Pérdidas y humos", fuel_kW - Q)]
        r.detalle = dict(Q_vapor_kW=Q, gas_kW_pcs=fuel_kW, gas_kgh=kg, gas_m3h=kg / float(self.v("densidad")), aire_kgh=air,
                         humos_kgh=kg + air, co2_kgh=kg * float(self.v("co2_kg_kg")), eta_pcs=self.eta_pcs,
                         masa_entra=kg + air, masa_sale=kg + air)
        return r


CATALOGO = [CalderaGas]
