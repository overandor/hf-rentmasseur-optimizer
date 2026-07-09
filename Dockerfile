FROM node:20-slim AS ui-builder
WORKDIR /jorki
COPY jorki/package.json jorki/package-lock.json ./
RUN npm ci
COPY jorki/ .
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

COPY --from=ui-builder /jorki/dist /app/jorki_ui_dist

RUN mkdir -p /tmp/systemlake_v4b

ENV PORT=7860
ENV SYSTEMLAKE_DATA_DIR=/tmp/systemlake_v4b
EXPOSE 7860

CMD ["python", "hf_space_app.py"]
