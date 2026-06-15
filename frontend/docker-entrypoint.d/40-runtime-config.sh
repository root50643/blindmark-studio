#!/bin/sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
cat > /usr/share/nginx/html/config.js <<EOF
window.__APP_CONFIG__ = {
  API_BASE_URL: "${API_BASE_URL}"
};
EOF
