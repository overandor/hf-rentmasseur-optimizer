FROM node:20-slim AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
RUN <<'EOF'
cat > /etc/nginx/conf.d/default.conf << 'NGINX'
server {
    listen 7860;
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
NGINX
EOF
EXPOSE 7860
CMD ["nginx", "-g", "daemon off;"]
