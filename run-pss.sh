#!/usr/bin/env bash
# Start PlanetarySystemStacker (CMOS fork) with its own Python environment.
#   ./run-pss.sh                     open the program
#   ./run-pss.sh --gui FILE.ser ...  open it with these files in the job list (CMOS Browser does this)
#   ./run-pss.sh install             create the Python environment (.env) with micromamba
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ${1:-} == install ]]; then
  MAMBA="${MAMBA:-$HOME/.local/bin/micromamba}"
  [[ -x $MAMBA ]] || { echo "micromamba not found at $MAMBA (install CMOS Browser first, it installs micromamba)"; exit 1; }
  "$MAMBA" create -y -q -p "$DIR/.env" -f "$DIR/environment-cmos.yml"
  echo "Installed. Start with: $DIR/run-pss.sh"
  exit 0
fi
[[ -x $DIR/.env/bin/python ]] || { echo "Not installed yet: run $DIR/run-pss.sh install"; exit 1; }
cd "$DIR/planetary_system_stacker"   # PSS imports its modules from this folder
exec "$DIR/.env/bin/python" planetary_system_stacker.py "$@"
