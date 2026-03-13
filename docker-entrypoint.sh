#!/bin/sh
# Fix volume permissions so the superset user can write to /app/.superset
chown -R superset:superset /app/.superset 2>/dev/null || true
exec gosu superset "$@"
