#!/bin/sh
set -eu
BAILONG_APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$HOME/.local/bin:$PATH"
# Keep the venv interpreter path so Python can find its installed dependencies.
if [ -x "$BAILONG_APP_DIR/.venv/bin/python" ]; then
    BAILONG_PYTHON="$BAILONG_APP_DIR/.venv/bin/python"
elif [ -n "${BAILONG_PYTHON:-}" ] && [ -x "$BAILONG_PYTHON" ]; then
    :
else
    printf '%s\n' '缺少运行环境。请先创建 .venv 并安装 requirements-linux.txt。' >&2
    exit 1
fi
exec "$BAILONG_PYTHON" "$BAILONG_APP_DIR/app/enhanced.py" "$@"
