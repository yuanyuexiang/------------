#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p /opt/jinbang/releases /opt/jinbang/backups
chmod 700 /opt/jinbang /opt/jinbang/backups
python3 - <<'PY'
import os
import secrets

path = '/opt/jinbang/.env'
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('Existing /opt/jinbang/.env preserved')
else:
    with os.fdopen(fd, 'w') as f:
        f.write('DEPLOY_DOMAIN=jinbang.matrix-net.tech\n')
        for name in ('POSTGRES_PASSWORD', 'JB_SECRET_KEY', 'JB_ADMIN_PASSWORD'):
            f.write(f'{name}={secrets.token_hex(32)}\n')
        f.write('LLM_BASE_URL=\nLLM_API_KEY=\nLLM_MODEL=\n')
    print('Created /opt/jinbang/.env with random credentials (mode 600)')
PY
