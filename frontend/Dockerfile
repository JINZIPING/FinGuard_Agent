FROM node:20-alpine AS build

WORKDIR /app

# Leave blank so App.js defaults to '/api', which Nginx proxies to the backend.
# Override at build time only if you need a direct cross-origin backend URL.
ARG REACT_APP_API_BASE_URL=
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
