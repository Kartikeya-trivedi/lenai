# ============================================================
# LenAI Nginx — Reverse Proxy & Static File Server
# ============================================================
# NOTE: Build context must be project root for playground access:
#   docker build -f nginx/Dockerfile .
# ============================================================
FROM nginx:alpine

LABEL maintainer="LenAI Team"
LABEL description="LenAI reverse proxy and playground static server"

# Remove default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy playground static files
RUN mkdir -p /usr/share/nginx/html/playground
COPY playground/ /usr/share/nginx/html/playground/

# Health check
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/nginx-health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

