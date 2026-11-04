"""Punto de entrada para Streamlit Community Cloud (PAT 135). Ejecuta la interfaz que está en «04 Interfaz Streamlit»."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "04 Interfaz Streamlit" / "app.py"), run_name="__main__")
