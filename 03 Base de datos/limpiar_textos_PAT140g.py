"""Limpia los textos ya sembrados en simulador_pat.db (PAT 140g, 17-11-2026).

La siembra usa INSERT OR IGNORE, así que reescribir los textos en el código no cambia una base que ya existe. Este script
aplica a la base la misma tabla de reemplazos del código (pat_sim/datos/textos_neutros.py) con UPDATE, columna por columna.

Uso:  python limpiar_textos_PAT140g.py ruta_a_la_db [--json] [--simular]

- Recorre todas las tablas de la base salvo las de datos de usuarios (proyectos y versiones de usuarios, corridas,
  cursos, estudiantes, entregas, usuarios y asignaciones).
- Solo cambia columnas de texto. Las columnas JSON (nombre terminado en _json) se dejan como están, salvo con --json:
  entonces se lee cada valor, se reemplaza solo dentro de los textos del JSON y se vuelve a escribir con
  json.dumps(ensure_ascii=False), el mismo formato de bd.a_json; un valor que no se lee como JSON no se toca.
- En la tabla proyectos solo cambia la descripción sembrada de la planta basada en Agrozzi (texto exacto de la siembra).
- Es idempotente: una segunda corrida cambia 0 filas.
- Imprime cuántas filas cambió por tabla. Con --simular no guarda nada (ROLLBACK).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "02 Motor de calculo Python"))
from pat_sim.datos.textos_neutros import neutralizar, _revisar_idempotencia  # noqa: E402

EXCLUIDAS = {"versiones", "corridas", "curso", "cursos", "estudiantes", "entregas", "usuarios", "usuarios_rol",
             "asignaciones", "sqlite_sequence"}
DESCRIPCION_SEMBRADA = ("Línea de pasta de tomate de la planta basada en Agrozzi (Empresas Carozzi S.A., Teno), "
                        "como en el Capítulo 1 y en Modelo_PAT_Agrozzi_v2.xlsx.")


def _excluida(tabla: str) -> bool:
    return tabla in EXCLUIDAS or tabla.startswith("proyectos_usuario") or tabla.startswith("sqlite_")


def _neutralizar_json(valor: str) -> str:
    try:
        d = json.loads(valor)
    except (TypeError, ValueError):
        return valor

    def rec(x):
        if isinstance(x, str):
            return neutralizar(x)
        if isinstance(x, list):
            return [rec(v) for v in x]
        if isinstance(x, dict):
            return {k: rec(v) for k, v in x.items()}
        return x

    nuevo = rec(d)
    return valor if nuevo == d else json.dumps(nuevo, ensure_ascii=False)


def limpiar(ruta: str | Path, con_json: bool = False, simular: bool = False) -> dict:
    malos = _revisar_idempotencia()
    if malos:
        raise RuntimeError(f"Tabla de reemplazos no idempotente: {malos}")
    cx = sqlite3.connect(str(ruta))
    cambios: dict[str, int] = {}
    try:
        tablas = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tablas:
            if _excluida(t):
                continue
            columnas = [(r[1], (r[2] or "").upper()) for r in cx.execute(f'PRAGMA table_info("{t}")')]
            filas_cambiadas: set[int] = set()
            for col, tipo in columnas:
                if tipo and "CHAR" not in tipo and "TEXT" not in tipo and "CLOB" not in tipo:
                    continue                                   # solo columnas de texto (o sin tipo declarado)
                es_json = col.lower().endswith("_json")
                if es_json and not con_json:
                    continue
                for rowid, v in cx.execute(f'SELECT rowid, "{col}" FROM "{t}"').fetchall():
                    if not isinstance(v, str):
                        continue
                    if t == "proyectos":
                        nuevo = neutralizar(v) if (col == "descripcion" and v == DESCRIPCION_SEMBRADA) else v
                    else:
                        nuevo = _neutralizar_json(v) if es_json else neutralizar(v)
                    if nuevo != v:
                        cx.execute(f'UPDATE "{t}" SET "{col}" = ? WHERE rowid = ?', (nuevo, rowid))
                        filas_cambiadas.add(rowid)
            cambios[t] = len(filas_cambiadas)
        if simular:
            cx.rollback()
        else:
            cx.commit()
    finally:
        cx.close()
    return cambios


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    ruta = Path(args[0])
    if not ruta.exists():
        print(f"No existe la base: {ruta}")
        return 1
    cambios = limpiar(ruta, con_json="--json" in argv, simular="--simular" in argv)
    total = 0
    for t, n in cambios.items():
        if n:
            print(f"{t}: {n} filas cambiadas")
            total += n
    print(f"Total: {total} filas cambiadas en {sum(1 for n in cambios.values() if n)} tablas"
          + (" (simulación, sin guardar)" if "--simular" in argv else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
