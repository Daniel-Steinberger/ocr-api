#!/usr/bin/env bash
# Serve-Launcher für ocr-api.
#
#   ./serve.sh <preset>     -> startet uvicorn mit dem gewählten Bind-Host
#   ./serve.sh              -> interaktive Auswahl (↑/↓ · Enter laden · Esc abbrechen)
#   ./serve.sh --list       -> verfügbare Presets mit Beschreibung
#
# Presets unterscheiden sich nur im Bind-Host:
#   - lan:   0.0.0.0  -> von anderen Rechnern im Netz erreichbar
#   - local: 127.0.0.1 -> nur von diesem Rechner erreichbar (z. B. hinter einem
#            eigenen Reverse-Proxy, oder wenn kein Netzwerkzugriff gewollt ist)
set -euo pipefail
cd "$(dirname "$0")"

# ─── .env laden (API_KEY, TORCH_DEVICE, ...) ────────────────────────────
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

PORT="${PORT:-8000}"

# Modelle laden (marker lädt ~5 GB nach VRAM). Ohne das startet der Server
# schnell, aber /convert und /jobs schlagen fehl, weil app.state.converter
# fehlt — nur für Tests/Smoke-Checks ohne echte OCR sinnvoll.
export OCR_API_LOAD_MODELS="${OCR_API_LOAD_MODELS:-1}"

# ─── Presets: name -> Bind-Host ──────────────────────────────────────────
declare -A HOST_PRESETS=(
  ["lan"]="0.0.0.0"
  ["local"]="127.0.0.1"
)

declare -A PRESET_DESC=(
  ["lan"]="Bind 0.0.0.0 · erreichbar von anderen Rechnern im Netz"
  ["local"]="Bind 127.0.0.1 · nur von diesem Rechner erreichbar"
)

MENU_ORDER=(lan local)

# ─── Interaktives Auswahlmenü via fzf (↑/↓ · Enter · Esc) ───────────────
CHOICE=""
choose_preset() {
  local options=("$@")
  local name desc lines="" picked

  if ! command -v fzf >/dev/null 2>&1; then
    echo "fzf nicht gefunden — bitte Preset als Argument angeben (./serve.sh <preset>)." >&2
    return 1
  fi
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "Kein interaktives Terminal — bitte Preset als Argument angeben (./serve.sh <preset>)." >&2
    return 1
  fi

  for name in "${options[@]}"; do
    desc="${PRESET_DESC[$name]:-}"
    lines+="$name"$'\t'"$desc"$'\n'
  done

  picked=$(printf '%s' "$lines" | fzf \
    --delimiter='\t' --with-nth=1 --no-multi --reverse --height='~40%' \
    --prompt='Bind-Host › ' \
    --header='↑/↓ wählen · Enter starten · Esc abbrechen' \
    --preview='printf "\033[1m%s\033[0m\n\n%s\n" {1} {2}' \
    --preview-window='down,4,wrap' --ansi) || return 1

  CHOICE="${picked%%$'\t'*}"
  [[ -n "$CHOICE" ]]
}

# ─── --list / --help ───────────────────────────────────────────────────
if [[ "${1:-}" == "--list" || "${1:-}" == "-l" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Presets (./serve.sh <preset>):"
  for name in "${MENU_ORDER[@]}"; do
    printf '  %-8s %s\n' "$name" "${PRESET_DESC[$name]:-}"
  done
  echo
  echo "Ohne Argument: interaktives Auswahlmenü."
  echo "Port über PORT=... env (Default 8000). Modelle laden per Default (OCR_API_LOAD_MODELS=0 zum Abschalten)."
  exit 0
fi

# ─── Preset bestimmen: Argument oder interaktive Auswahl ────────────────
SEL="${1:-}"
if [[ -z "$SEL" ]]; then
  if choose_preset "${MENU_ORDER[@]}"; then
    SEL="$CHOICE"
    echo ">> Gewählt: $SEL"
    echo
  else
    echo "Abgebrochen — Server nicht gestartet." >&2
    exit 130
  fi
fi

HOST="${HOST_PRESETS[$SEL]:-}"
if [[ -z "$HOST" ]]; then
  echo "Unbekanntes Preset: '$SEL'" >&2
  echo "Verfügbar: $(printf '%s ' "${MENU_ORDER[@]}")" >&2
  echo "Details:   ./serve.sh --list" >&2
  exit 1
fi

echo ">> Bind    : $HOST:$PORT (Preset '$SEL')"
echo ">> Modelle : $([[ "$OCR_API_LOAD_MODELS" == "1" ]] && echo "laden (OCR_API_LOAD_MODELS=1)" || echo "NICHT laden — /convert und /jobs funktionieren nicht")"
echo

exec uv run uvicorn ocr_api.main:app --host "$HOST" --port "$PORT"
