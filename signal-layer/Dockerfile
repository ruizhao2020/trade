FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG APP_MODE=private
ARG VITE_API_BASE=http://localhost:8000/api/v1
ENV VITE_API_BASE=$VITE_API_BASE
RUN if [ "$APP_MODE" = "public" ]; then npm run build:public && cp -R dist-public dist; else npm run build:private && cp -R dist-private dist; fi

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
