"""Arma simulador_pat.db desde cero: esquema, proyecto «Planta basada en Agrozzi», fuentes del Capítulo 1 y catálogo de parámetros.

Uso (desde cualquier carpeta):
    python construir_bd.py                 # usa el índice v3 de PAT\\Fuentes\\Capitulo 1 2.0 si existe
    python construir_bd.py --indice RUTA   # otro índice de fuentes

La base se arma en una carpeta temporal y se copia al final, para no dejar archivos de bloqueo en la carpeta sincronizada.
"""
from __future__ import annotations
import argparse, shutil, sys, tempfile
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent                              # …\Aplicacion simulador
sys.path.insert(0, str(RAIZ / "02 Motor de calculo Python"))

from pat_sim.datos import bd as bdmod, fuentes_indice   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indice", default=str(RAIZ.parent / "Fuentes" / "Capitulo 1 2.0" / "00_INDICE_FUENTES_v3.md"))
    ap.add_argument("--destino", default=str(AQUI / "simulador_pat.db"))
    a = ap.parse_args()
    if Path(a.indice).exists():
        n = fuentes_indice.armar_csv(a.indice, bdmod.CSV_FUENTES)
        print(f"Fuentes leídas del índice: {n} (guardadas en {bdmod.CSV_FUENTES.name})")
    else:
        print(f"No encuentro el índice {a.indice}; se usa el CSV que ya está en el paquete")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / "simulador_pat.db"
        base = bdmod.BaseDatos(tmp)
        print("Precarga:", base.precargar())
        print("Contenido:", base.contar())
        destino = Path(a.destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():   # respaldo con fecha: la base nueva reemplaza las versiones guardadas desde la interfaz (revisión PAT 125, A09)
            resp = destino.with_name(destino.stem + "_respaldo_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
            shutil.copyfile(destino, resp); print("Respaldo de la base anterior:", resp)
        shutil.copyfile(tmp, destino)
    print("Base guardada en", destino)


if __name__ == "__main__":
    main()
