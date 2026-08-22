#!/usr/bin/env bash
set -euo pipefail
exec sg lxd -c "snapcraft pack"
