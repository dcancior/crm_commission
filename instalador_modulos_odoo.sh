#!/usr/bin/env bash
set -euo pipefail

# ===== Config =====
CNT="goodcar_odoo16_produccion"     # Contenedor Odoo
PGCNT="goodcar_psql_produccion"     # Contenedor Postgres
DB="goodcar_prod"                   # Base de datos Odoo

# Odoo -> Postgres (desde el contenedor de Odoo)
DB_HOST="postgres"
DB_PORT="5432"
DB_USER="odoo"
DB_PASS='1Q2W3E0o9i8u.ASWOVH'

# Postgres CLI (psql) dentro del contenedor de Postgres:
PG_HOST="127.0.0.1"
PG_PORT="5432"

# Rutas extra de addons (si tu módulo no está en las rutas por defecto del contenedor Odoo):
ADDONS_PATH="${ADDONS_PATH:-}"      # ej: "/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons"

# ===== Lista de módulos disponibles =====
AVAILABLE_MODULES=(
  "workshop_mechanic"
  "cdfi_invoice"
  "crm_commission"
  "config_goodcar"
  "product_pack"
  "sale_product_pack"
)

# ===== Helpers =====
msg(){ echo -e "\n==> $*"; }

detect_odoo_cmd() {
  if docker exec "$CNT" bash -lc 'command -v odoo >/dev/null 2>&1'; then
    echo "odoo"; return
  fi
  if docker exec "$CNT" bash -lc 'python3 - <<PY
import importlib,sys
sys.exit(0 if importlib.util.find_spec(\"odoo\") else 1)
PY
'; then
    echo "python3 -m odoo"; return
  fi
  echo ""
}

ODOO_CMD="$(detect_odoo_cmd)"
if [[ -z "$ODOO_CMD" ]]; then
  echo "No encontré 'odoo' ni el módulo Python 'odoo' dentro de $CNT. Revisa tu imagen."
  exit 1
fi

odoo_args() {
  local args=""
  if docker exec "$CNT" test -f /etc/odoo/odoo.conf; then
    args="-c /etc/odoo/odoo.conf"
  fi
  echo "${args} --db_host=${DB_HOST} --db_port=${DB_PORT} --db_user=${DB_USER} --db_password=\"${DB_PASS}\""
}

with_addons_path() {
  [[ -n "$ADDONS_PATH" ]] && echo "--addons-path=${ADDONS_PATH}" || echo ""
}

mask_pass() {
  local s="$1"
  [[ -n "${DB_PASS:-}" ]] && s="${s//${DB_PASS}/******}"
  echo "$s"
}

restart_odoo(){ msg "Reiniciando $CNT..."; docker restart "$CNT" >/dev/null; msg "Listo."; }

verify_module(){
  msg "Estado del/los módulo(s) en '${DB}':"
  IFS=',' read -ra __mods <<< "$MODS"
  for m in "${__mods[@]}"; do
    docker exec -it "$PGCNT" psql \
      -h "$PG_HOST" -p "$PG_PORT" \
      -U "$DB_USER" -d "$DB" -tAc \
      "SELECT name, state, latest_version FROM ir_module_module WHERE name='${m}';" || true
  done
}

clean_assets(){
  msg "Eliminando bundles de assets cacheados en DB..."
  docker exec -it "$PGCNT" psql \
    -h "$PG_HOST" -p "$PG_PORT" \
    -U "$DB_USER" -d "$DB" -c \
    "DELETE FROM ir_attachment WHERE name LIKE '/web/assets/%' OR url LIKE '/web/%assets%';"
}

run_odoo() {
  local action="$1"          # -i o -u
  local extra="${2:-}"       # ej. --without-demo=all
  local cmd="${ODOO_CMD} $(odoo_args) $(with_addons_path) -d '${DB}' ${action} '${MODS}' ${extra} --stop-after-init"
  local log_cmd; log_cmd="$(mask_pass "$cmd")"
  msg "Ejecutando dentro de ${CNT}: ${log_cmd}"
  docker exec -it "$CNT" bash -lc "${cmd}"
}

install_module(){ run_odoo "-i" "--without-demo=all"; restart_odoo; verify_module; }
update_module(){ run_odoo "-u"; restart_odoo; verify_module; }

choose_modules() {
  echo "==== Selecciona módulo(s) ===="
  local i=1
  for m in "${AVAILABLE_MODULES[@]}"; do
    printf "  %d) %s\n" "$i" "$m"
    ((i++))
  done
  echo "  m) Varios (escribe nombres separados por comas)"
  echo "  o) Otro (escribe el nombre manualmente)"
  echo

  while true; do
    read -rp "Opción: " ans
    case "$ans" in
      [1-9]|[1-9][0-9])
        local idx=$((ans-1))
        if (( idx>=0 && idx<${#AVAILABLE_MODULES[@]} )); then
          MODS="${AVAILABLE_MODULES[$idx]}"
          break
        else
          echo "Número fuera de rango."
        fi
        ;;
      m|M)
        read -rp "Escribe los módulos separados por comas (ej. mod1,mod2,mod3): " MODS
        MODS="${MODS// /}"   # quita espacios
        [[ -z "$MODS" ]] && { echo "Debes escribir al menos un módulo."; continue; }
        break
        ;;
      o|O)
        read -rp "Nombre del módulo: " MODS
        MODS="${MODS// /}"
        [[ -z "$MODS" ]] && { echo "Debes escribir un nombre."; continue; }
        break
        ;;
      *)
        echo "Opción inválida."
        ;;
    esac
  done

  echo -e "\nMódulo(s) seleccionado(s): $MODS"
}

# ===== Flow =====
echo "Contenedor Odoo : $CNT"
echo "Contenedor PG   : $PGCNT"
echo "Base de datos   : $DB"
echo "Comando Odoo    : $ODOO_CMD"
echo "DB_HOST/PORT    : $DB_HOST:$DB_PORT (desde Odoo)"
echo "PG_HOST/PORT    : $PG_HOST:$PG_PORT (psql en contenedor PG)"
[[ -n "$ADDONS_PATH" ]] && echo "ADDONS_PATH     : $ADDONS_PATH"
echo

choose_modules
echo

PS3=$'\n'"Elige una opción (1-6): "
options=(
  "Instalar (primera vez)"
  "Reinstalar / Actualizar"
  "Instalar + limpiar assets"
  "Reinstalar + limpiar assets"
  "Solo limpiar assets"
  "Verificar estado del módulo"
)
select opt in "${options[@]}"; do
  case "$REPLY" in
    1) install_module; break ;;
    2) update_module; break ;;
    3) install_module; clean_assets; restart_odoo; break ;;
    4) update_module; clean_assets; restart_odoo; break ;;
    5) clean_assets; restart_odoo; verify_module; break ;;
    6) verify_module; break ;;
    *) echo "Opción inválida, intenta de nuevo." ;;
  esac
done

