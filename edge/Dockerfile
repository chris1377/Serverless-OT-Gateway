# Usa un'immagine Python ufficiale e leggera
FROM python:3.11-slim

# Imposta la directory di lavoro
WORKDIR /app

# Installa le dipendenze
RUN pip install --no-cache-dir asyncua aiohttp

# Copia il codice del gateway nel container
COPY Serverless_Gateway.py .

# Comando di avvio
CMD ["python", "Serverless_Gateway.py"]