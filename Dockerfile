FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wardzero ./wardzero
COPY web ./web
COPY tests ./tests
COPY sample_data ./sample_data
# Train the interpretable risk model on synthetic episodes at build time (~20 s) so startup is instant.
RUN python -m wardzero.train
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "wardzero.main:app", "--host", "0.0.0.0", "--port", "8000"]
