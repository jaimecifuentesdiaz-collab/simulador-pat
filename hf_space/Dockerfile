# Simulador PAT en Hugging Face Spaces (PAT 138, T25, 13-11-2026). Plantilla Docker, porque Hugging Face ya no ofrece
# Streamlit como SDK propio. El código sale de la rama «hf» del repositorio de GitHub; la línea ADD hace que el espacio
# vuelva a bajar el código cada vez que esa rama cambia.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 PAT_ACCESO=usuarios
WORKDIR /home/user/app
ADD --chown=user https://github.com/jaimecifuentesdiaz-collab/simulador-pat/commits/hf.atom /home/user/version_rama.atom
RUN git clone --depth 1 --branch hf https://github.com/jaimecifuentesdiaz-collab/simulador-pat.git .
RUN pip install --no-cache-dir --user -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
