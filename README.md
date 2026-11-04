# Simulador PAT: diseño asistido de ingeniería básica

Proyecto de Aplicación Tecnológica de Jaime Andrés Cifuentes Díaz, Ingeniería Civil Industrial, Universidad de Talca, campus Curicó. Profesor: Carlos Torres Fuchslocher.

Aplicación en Python y Streamlit para diseñar una planta a partir de un desafío (producto, demanda y precios de venta): balances, recuperación de calor, instrumentación ISA, costeo con índice de Williams y CEPCI, layout con elevaciones, evaluación económica y Montecarlo de confiabilidad y demanda. Caso base: planta de pasta de tomate basada en Agrozzi (Teno, Región del Maule), y plantas de pellet, chip y leña.

## Ejecutar en el computador
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Publicar en Streamlit Community Cloud
1. Subir este repositorio a GitHub.
2. En https://share.streamlit.io elegir el repositorio, rama `main`, archivo `streamlit_app.py` y Python 3.12.
3. En *Advanced settings* > *Secrets* pegar el contenido de `.streamlit/secrets.toml.ejemplo` con las claves reales.

La base SQLite incluida es la semilla: en la nube se reinicia cuando la aplicación se reinicia. Los datos permanentes irán en Supabase.
