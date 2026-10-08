# Development server for the local profile; Vite proxies /api to the api service.
FROM node:22-bookworm-slim
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
