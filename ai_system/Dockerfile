FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY ai_system/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_system ./ai_system
COPY backend/ml ./ml

# Retrain ML models at build time so they match the installed scikit-learn version.
# The script auto-saves to /app/ml/models/ (SCRIPT_DIR/models).
RUN python /app/ml/train_risk_model.py && echo "✅ ML models trained successfully" || echo "⚠️ ML training failed — rules-only fallback active"

EXPOSE 8000

CMD ["uvicorn", "ai_system.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
