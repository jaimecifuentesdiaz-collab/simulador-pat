"""PAT 145 (20-11-2026): las pruebas de la interfaz nunca leen el .streamlit/secrets.toml real.

Con las claves verdaderas, la aplicación busca precios en Tavily (gasta créditos y cambia los candidatos) y entra a Supabase
en vez de quedar en «Modo local», y tres pruebas fallaban en Windows. AppTest solo reemplaza st.secrets cuando su diccionario
secrets no está vacío: se le pone una marca sin claves. Las pruebas que necesitan claves las dan con variables de entorno
(monkeypatch.setenv), que la aplicación lee cuando st.secrets no las tiene."""
from streamlit.testing.v1 import AppTest

_init = AppTest.__init__


def _init_sin_secretos(self, *a, **k):
    _init(self, *a, **k)
    self.secrets = {"PAT_PRUEBAS": "sin secretos reales"}


AppTest.__init__ = _init_sin_secretos
