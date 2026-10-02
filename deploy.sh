#!/usr/bin/env bash
# Configure simplified output for the IBus Rime luna_pinyin_simp schema.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash deploy.sh [--no-restart] [--set-default]

  --no-restart   Deploy only; run `ibus restart` yourself later.
  --set-default  Also make luna_pinyin_simp the first schema in default.custom.yaml.

Run as your desktop user. Requires IBus Rime, rime_deployer and python3-yaml.
Environment overrides: RIME_USER_DIR, RIME_SHARED_DIR, RIME_PYTHON.
EOF
}

restart=1
set_default=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) restart=0 ;;
    --set-default) set_default=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg. Use --help." >&2; exit 2 ;;
  esac
done
[[ $EUID -ne 0 ]] || { echo 'Run as your desktop user, without sudo.' >&2; exit 1; }

python_bin="${RIME_PYTHON:-/usr/bin/python3}"
rime_dir="${RIME_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/ibus/rime}"
shared_dir="${RIME_SHARED_DIR:-/usr/share/rime-data}"
for command_name in rime_deployer ibus; do
  command -v "$command_name" >/dev/null || { echo "Missing command: $command_name" >&2; exit 1; }
done
"$python_bin" -c 'import yaml' || { echo 'Install python3-yaml first.' >&2; exit 1; }
[[ -f "$shared_dir/luna_pinyin_simp.schema.yaml" ]] || {
  echo "Missing schema: $shared_dir/luna_pinyin_simp.schema.yaml" >&2; exit 1;
}

build() {
  rime_deployer --build "$rime_dir" "$shared_dir" "$rime_dir/build"
}

mkdir -p "$rime_dir"
if [[ ! -f "$rime_dir/build/default.yaml" ]]; then
  echo 'No compiled Rime configuration found; running initial deployment.'
  build || { echo 'Initial deployment failed.' >&2; exit 1; }
fi

"$python_bin" - "$rime_dir" "$set_default" <<'PY'
import datetime
import os
from pathlib import Path
import shutil
import sys
import tempfile
import yaml

root = Path(sys.argv[1])
set_default = sys.argv[2] == '1'
SCHEMA = 'luna_pinyin_simp'


def load_mapping(path):
    data = yaml.safe_load(path.read_text()) if path.exists() else None
    data = data or {}
    if not isinstance(data, dict):
        sys.exit(f'{path} must be a YAML mapping; no files changed.')
    patch = data.setdefault('patch', {})
    if not isinstance(patch, dict):
        sys.exit(f'patch in {path} must be a YAML mapping; no files changed.')
    return data, patch


def save(path, data):
    if path.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = path.with_name(path.name + '.bak-' + stamp)
        shutil.copy2(path, backup)
        print(f'Backup: {backup}', flush=True)
    fd, temporary = tempfile.mkstemp(prefix='.simplified-', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
        if path.exists():
            shutil.copymode(path, temporary)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Updated: {path}', flush=True)


# Validate everything before writing anything.
defaults = yaml.safe_load((root / 'build/default.yaml').read_text()) or {}
enabled = [item.get('schema') for item in defaults.get('schema_list', []) if isinstance(item, dict)]
default_target = root / 'default.custom.yaml'
default_data = None
if set_default:
    default_data, default_patch = load_mapping(default_target)
    schema_list = default_patch.get('schema_list')
    if schema_list is None:
        schema_list = [{'schema': name} for name in enabled]
    if not isinstance(schema_list, list) or not all(isinstance(s, dict) for s in schema_list):
        sys.exit('Unsupported schema_list in default.custom.yaml; no files changed.')
    default_patch['schema_list'] = [{'schema': SCHEMA}] + [
        s for s in schema_list if s.get('schema') != SCHEMA]
elif SCHEMA not in enabled:
    sys.exit(f'{SCHEMA} is not enabled. Re-run with --set-default, or add it to '
             'schema_list in default.custom.yaml and deploy first.')

target = root / f'{SCHEMA}.custom.yaml'
created = not target.exists()
data, patch = load_mapping(target)
switches = patch.get('switches')
if switches is None:
    schema = yaml.safe_load((root / f'build/{SCHEMA}.schema.yaml').read_text())
    switches = schema.get('switches', [])
    if created:
        # Drop the stock toggle that the dedicated switch below replaces.
        old_option = (schema.get('simplifier') or {}).get('option_name')
        switches = [s for s in switches if not isinstance(s, dict) or s.get('name') != old_option]
if not isinstance(switches, list) or not all(isinstance(s, dict) for s in switches):
    sys.exit('Unsupported switches configuration; no files changed.')
patch['switches'] = [s for s in switches if s.get('name') != 'simplified_output']
patch['switches'].append({'name': 'simplified_output', 'reset': 1})
patch['simplifier/option_name'] = 'simplified_output'
patch['simplifier/opencc_config'] = 't2s.json'

if default_data is not None:
    save(default_target, default_data)
save(target, data)
PY

if ! build; then
  echo 'Deployment failed. Backup paths are printed above; see README.md for recovery.' >&2
  exit 1
fi
"$python_bin" - "$rime_dir/build/luna_pinyin_simp.schema.yaml" <<'PY'
import sys
import yaml
with open(sys.argv[1]) as stream:
    schema = yaml.safe_load(stream)
assert schema['simplifier']['option_name'] == 'simplified_output', 'Option was not deployed'
assert schema['simplifier']['opencc_config'] == 't2s.json', 'Conversion rule was not deployed'
assert any(s.get('name') == 'simplified_output' and s.get('reset') == 1
           for s in schema['switches']), 'Default-on switch was not deployed'
print('Compiled configuration verified.')
PY

if [[ $restart -eq 0 ]]; then
  echo 'Deployment complete. Run ibus restart when ready, then select the simplified Pinyin schema.'
  exit 0
fi
ibus restart
for attempt in {1..15}; do
  if ibus engine rime >/dev/null 2>&1 && [[ "$(ibus engine 2>/dev/null)" == rime ]]; then
    echo 'Rime is running. Select 拼音（简体） if needed, then test: 中文输入法.'
    exit 0
  fi
  sleep 1
done
echo 'Configuration deployed, but IBus could not be confirmed ready. See README.md.' >&2
exit 1
