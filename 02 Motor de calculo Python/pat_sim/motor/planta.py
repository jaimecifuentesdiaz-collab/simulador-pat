"""Planta: equipos conectados por corrientes. Resuelve en orden topológico, aplica especificaciones de diseño
(como en un simulador de procesos) y verifica los cierres de materia y energía de cada equipo."""
from __future__ import annotations
from dataclasses import dataclass, field
from .corrientes import Corriente, mezclar, Residual
from .equipos import Equipo, Sumidero

TIPOS_SERVICIO = ("vapor", "electricidad", "gas", "aire", "calor")


@dataclass
class Conexion:
    origen: str; puerto_origen: str; destino: str; puerto_destino: str; reparto: float = 100.0
    nombre: str = ""   # número de corriente (ISO 10628: se numera en el diagrama)


@dataclass
class EspecDiseno:
    """Ajusta un parámetro de un equipo para que una propiedad de la entrada de otro equipo alcance un valor."""
    equipo_var: str; param: str; equipo_obj: str; propiedad: str; valor: float
    descripcion: str = ""


@dataclass
class Instrumento:
    """Instrumento o lazo según ISA-5.1. tag: letras (por ejemplo TIC); numero: número de lazo."""
    letras: str; numero: str; equipo: str; ubicacion: str = "panel"   # campo, panel, dcs, plc
    descripcion: str = ""; parametro: str | None = None; elemento_final: str | None = None
    # PAT 134: lienzo de Diseño. Todos opcionales, con valor por defecto, para que las versiones guardadas antes (sin estos
    # campos) se carguen igual. x, y: centro del símbolo en el lienzo (None: junto a su equipo); simbolo: clave de forma de
    # isa51 ("" = burbuja según la ubicación, como antes); conexiones: líneas de señal ISA-5.1 que salen de este instrumento,
    # cada una {"senal", "tipo" (equipo, corriente o instrumento), "destino", "parametro"}.
    x: float | None = None; y: float | None = None; simbolo: str = ""
    conexiones: list = field(default_factory=list)


class Planta:
    def __init__(self, nombre: str = "Planta", rubro: str = "general"):
        self.nombre = nombre; self.rubro = rubro
        self.equipos: dict[str, Equipo] = {}
        self.conexiones: list[Conexion] = []
        self.especs: list[EspecDiseno] = []
        self.instrumentos: list[Instrumento] = []
        self.globales: dict = dict(T_final_residual=30.0, dT_min=5.0)
        self.resuelta = False; self.avisos: list[str] = []

    # ---------- edición
    def agregar(self, eq: Equipo) -> Equipo:
        if eq.id in self.equipos:
            raise ValueError(f"Ya existe el equipo {eq.id}")
        self.equipos[eq.id] = eq; return eq

    def quitar(self, id: str):
        self.equipos.pop(id)
        self.conexiones = [c for c in self.conexiones if c.origen != id and c.destino != id]

    def conectar(self, origen, puerto_origen, destino, puerto_destino, reparto=100.0, nombre=""):
        a, b = self.equipos[origen], self.equipos[destino]
        if puerto_origen not in [p.nombre for p in a.salidas]:
            raise ValueError(f"{origen} no tiene el puerto de salida {puerto_origen}")
        if puerto_destino not in [p.nombre for p in b.entradas]:
            raise ValueError(f"{destino} no tiene el puerto de entrada {puerto_destino}")
        c = Conexion(origen, puerto_origen, destino, puerto_destino, reparto, nombre)
        self.conexiones.append(c); return c

    def tipo_conexion(self, c: Conexion) -> str:
        return next(p.tipo for p in self.equipos[c.origen].salidas if p.nombre == c.puerto_origen)

    def es_servicio(self, c: Conexion) -> bool:
        return self.tipo_conexion(c) in TIPOS_SERVICIO

    # ---------- resolución
    def orden(self) -> list[str]:
        proc = [c for c in self.conexiones if not self.es_servicio(c)]
        indeg = {k: 0 for k in self.equipos}
        for c in proc: indeg[c.destino] += 1
        cola = [k for k, d in indeg.items() if d == 0]; orden = []
        while cola:
            k = cola.pop(0); orden.append(k)
            for c in proc:
                if c.origen == k:
                    indeg[c.destino] -= 1
                    if indeg[c.destino] == 0: cola.append(c.destino)
        if len(orden) != len(self.equipos):
            raise ValueError("La planta tiene un ciclo de corrientes de proceso; declare la recirculación como especificación")
        return orden

    def _resolver_una_vez(self):
        self.avisos = []
        salidas: dict[tuple[str, str], Corriente] = {}
        for k in self.orden():
            eq = self.equipos[k]
            if eq.tipo.startswith("caldera"):
                continue
            ent = {}
            for p in eq.entradas:
                cs = [salidas[(c.origen, c.puerto_origen)].fraccion(c.reparto / 100)
                      for c in self.conexiones if c.destino == k and c.puerto_destino == p.nombre and not self.es_servicio(c)
                      and (c.origen, c.puerto_origen) in salidas]
                if cs: ent[p.nombre] = mezclar(cs)
            faltan = [p.nombre for p in eq.entradas if p.tipo not in TIPOS_SERVICIO and p.nombre not in ent]
            if faltan:
                raise ValueError(f"{k} ({eq.nombre}) no tiene alimentación en {', '.join(faltan)}")
            eq.resultado = eq.calcular(ent)
            ce = eq.params["consumo_especifico"].valor if "consumo_especifico" in eq.params else None
            if ce:                                  # consumo eléctrico declarado por el usuario (kWh/t × t/h = kW)
                carga = eq.resultado.detalle.get("carga_t_h") or 0.0
                eq.resultado.servicios["electricidad_kW"] = eq.resultado.servicios.get("electricidad_kW", 0.0) + float(ce) * carga
            self.avisos += eq.resultado.avisos
            for pn, cor in eq.resultado.salidas.items():
                salidas[(k, pn)] = cor
            for pn in [p.nombre for p in eq.salidas]:
                total = sum(c.reparto for c in self.conexiones if c.origen == k and c.puerto_origen == pn)
                if total > 100.01:
                    self.avisos.append(f"{k}: el reparto del puerto {pn} suma {total:.1f} %")
        # servicios: calderas y generadores de calor al final, con la demanda de los equipos conectados a su puerto
        # de vapor (tomate) o de calor (aire de secado de la biomasa): servicio «vapor_kW» o «calor_kW» del destino
        for k, eq in self.equipos.items():
            if eq.tipo.startswith("caldera"):
                dem = sum(self.equipos[c.destino].resultado.servicios.get(c.puerto_origen + "_kW", 0.0) * c.reparto / 100
                          for c in self.conexiones if c.origen == k and c.puerto_origen in ("vapor", "calor") and self.equipos[c.destino].resultado)
                eq.resultado = eq.calcular({"_demanda_vapor_kW": dem, "_demanda_kW": dem})
        self.salidas = salidas
        self.resuelta = True

    def resolver(self, tol=1e-10, maxit=60):
        self._resolver_una_vez()
        for es in self.especs:
            eqv = self.equipos[es.equipo_var]
            x_ini = eqv.v(es.param)                  # PAT 134: último valor con el que la planta se resolvió
            def f(x):
                eqv.set(es.param, x); self._resolver_una_vez()
                return self.propiedad_entrada(es.equipo_obj, es.propiedad) - es.valor
            try:
                x0 = float(eqv.v(es.param)); x1 = x0 * 1.01
                f0, f1 = f(x0), f(x1)
                for _ in range(maxit):
                    if abs(f1) < tol: break
                    if f1 == f0: break
                    x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
                    x0, f0 = x1, f1; x1 = x2; f1 = f(x1)
                else:
                    self.avisos.append(f"La especificación {es.descripcion or es.param} no convergió")
                self._validar_balance()
            except ValueError as e:                  # PAT 134: la especificación pide algo físicamente imposible
                # PAT 134 (equipo G): el error también puede venir de un equipo durante la búsqueda (por ejemplo, una concentración
                # de salida negativa en el evaporador). Se devuelve el parámetro a su último valor para que, al corregir la
                # especificación, la búsqueda parta de un punto factible y la planta se pueda resolver de nuevo.
                eqv.set(es.param, x_ini)
                try:
                    self._resolver_una_vez()
                except ValueError:
                    pass
                valor_txt = f"{es.valor:g}".replace(".", ",")
                raise ValueError(f"La especificación «{es.descripcion or es.param}» = {valor_txt} no se puede alcanzar: {e}") from None
        self._validar_balance()
        return self

    def _validar_balance(self, tol: float = 1e-6):
        """PAT 134: un parámetro imposible (por ejemplo 0 °Brix en la pasta o en el jugo) no debe dar una planta «resuelta»
        con caudales negativos o concentraciones fuera de 0 a 1: se rechaza con un mensaje que dice qué corriente falla."""
        for (eq, puerto), c in self.salidas.items():
            m, s_ = float(c.m), float(c.s)
            if m < -tol or s_ < -tol or (m > tol and not -tol <= s_ / m <= 1 + tol):
                nombre = self.equipos[eq].nombre if eq in self.equipos else eq
                raise ValueError(f"la salida «{puerto}» de {eq} ({nombre}) queda con caudal {m:,.0f} kg/h y sólidos {s_:,.0f} kg/h, "
                                 "que no existen físicamente; revise el °Brix o la concentración que cambió")

    def corriente_entrada(self, equipo: str) -> Corriente:
        cs = [self.salidas[(c.origen, c.puerto_origen)].fraccion(c.reparto / 100) for c in self.conexiones
              if c.destino == equipo and not self.es_servicio(c)]
        return mezclar(cs)

    def propiedad_entrada(self, equipo: str, prop: str) -> float:
        c = self.corriente_entrada(equipo)
        return float(getattr(c, prop))

    # ---------- resultados
    def residuales(self, solo_mapa=True) -> list[Residual]:
        out = []
        for eq in self.equipos.values():
            if eq.resultado:
                out += [r for r in eq.resultado.residuales if (r.en_mapa or not solo_mapa)]
        return out

    def sumideros(self) -> list[Sumidero]:
        out = []
        for eq in self.equipos.values():
            if eq.resultado: out += eq.resultado.sumideros
        return out

    def servicio_total(self, clave: str) -> float:
        return sum(eq.resultado.servicios.get(clave, 0.0) for eq in self.equipos.values() if eq.resultado)

    def cierres(self) -> list[dict]:
        """Cierre de materia y energía de cada equipo (entrada − salida)."""
        filas = []
        for k in self.orden():
            eq = self.equipos[k]; r = eq.resultado
            if r is None: continue
            if eq.tipo.startswith("caldera"):
                m_in = r.detalle.get("masa_entra", 0.0); m_out = r.detalle.get("masa_sale", 0.0); s_in = s_out = 0.0
            else:
                ent = [self.salidas[(c.origen, c.puerto_origen)].fraccion(c.reparto / 100) for c in self.conexiones
                       if c.destino == k and not self.es_servicio(c)]
                # el vapor vivo (tomate) y el aire de secado (biomasa) entran como servicio
                m_in = sum(c.m for c in ent) + r.servicios.get("vapor_kgh", 0.0) + r.servicios.get("aire_kgh", 0.0); s_in = sum(c.s for c in ent)
                m_out = sum(c.m for c in r.salidas.values()); s_out = sum(c.s for c in r.salidas.values())
                if not ent:   # alimentación de la planta
                    m_in, s_in = m_out, s_out
                # el tomate entero se modela con cp fijo y sin °Brix: el °Brix se fija en el jugo (refinadora)
                if any(c.cp is not None and c.s == 0 for c in ent) and s_out > 0:
                    s_in = s_out = None
            filas.append(dict(equipo=k, nombre=eq.nombre, masa_entra=m_in, masa_sale=m_out, cierre_masa=m_in - m_out,
                              solidos_entra=s_in, solidos_sale=s_out, cierre_solidos=None if s_in is None else s_in - s_out,
                              energia_entra=sum(v for _, v in r.energia_in), energia_sale=sum(v for _, v in r.energia_out),
                              cierre_energia=r.cierre_energia()))
        return filas

    def utilizaciones(self) -> list[dict]:
        out = []
        for eq in self.equipos.values():
            u = eq.utilizacion()
            if u is not None: out.append(dict(equipo=eq.id, nombre=eq.nombre, utilizacion=u))
        return sorted(out, key=lambda d: -d["utilizacion"])

    def a_dict(self) -> dict:
        return dict(nombre=self.nombre, rubro=self.rubro, globales=self.globales,
                    equipos=[e.a_dict() for e in self.equipos.values()],
                    conexiones=[c.__dict__ for c in self.conexiones], especs=[e.__dict__ for e in self.especs],
                    instrumentos=[i.__dict__ for i in self.instrumentos])
