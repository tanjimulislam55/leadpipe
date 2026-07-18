FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY leadpipe/ leadpipe/
COPY *.py ./

ENV PYTHONUNBUFFERED=1
CMD ["streamlit", "run", "dashboard.py", "--server.headless", "true", "--server.address", "0.0.0.0"]
