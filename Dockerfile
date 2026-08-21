# ---- frontend ----
FROM node:22-alpine AS webbuild
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---- backend ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/seed ./seed
COPY --from=webbuild /build/dist ./frontend/dist
ENV SPOOL_FRONTEND_DIST=/app/frontend/dist SPOOL_SEED_DIR=/app/seed SPOOL_DATA_DIR=/data
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV SPOOL_BUILD_SHA=$GIT_SHA SPOOL_BUILD_TIME=$BUILD_TIME
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
