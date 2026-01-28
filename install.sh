#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Kjør som root: sudo ./install.sh" >&2
  exit 1
fi

chmod +x ./interheart.sh
./interheart.sh install

echo ""
echo "OK. Neste:"
echo "  sudo /usr/local/bin/interheart add <name> <ip> <endpoint_url>"
echo "  sudo /usr/local/bin/interheart enable"
echo "WebUI (valgfritt): se webui/README.md"
