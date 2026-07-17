FROM python:3.12-slim

WORKDIR /app

# Installed separately from the rest of the source so dependency layers are
# only rebuilt when requirements.txt actually changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
