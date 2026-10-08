#!/usr/bin/env bash
# Add Xense terminology dictionaries to an existing Fcitx5 Rime Ice setup.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash deploy.sh [--no-reload] [--set-default] [--no-english]

  --no-reload   Deploy only; reload Fcitx5 yourself later.
  --set-default Put rime_ice first in default.custom.yaml (other schemas are preserved).
  --no-english  Disable this project's supplemental English candidates.

Run as your desktop user. Requires Fcitx5 Rime, an existing Rime Ice installation,
rime_deployer and python3-yaml.
Environment overrides: RIME_USER_DIR, RIME_SHARED_DIR, RIME_PYTHON,
RIME_ENGLISH_WORDLIST and FCITX5_REMOTE.
EOF
}

reload=1
set_default=0
english=1
for arg in "$@"; do
  case "$arg" in
    --no-reload|--no-restart) reload=0 ;;
    --set-default) set_default=1 ;;
    --no-english) english=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg. Use --help." >&2; exit 2 ;;
  esac
done
[[ $EUID -ne 0 ]] || { echo 'Run as your desktop user, without sudo.' >&2; exit 1; }

python_bin="${RIME_PYTHON:-/usr/bin/python3}"
rime_dir="${RIME_USER_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/fcitx5/rime}"
shared_dir="${RIME_SHARED_DIR:-/usr/share/rime-data}"
wordlist="${RIME_ENGLISH_WORDLIST:-/usr/share/dict/words}"
fcitx5_remote="${FCITX5_REMOTE:-fcitx5-remote}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v rime_deployer >/dev/null || { echo 'Missing command: rime_deployer' >&2; exit 1; }
if [[ $reload -eq 1 ]]; then
  command -v "$fcitx5_remote" >/dev/null || { echo "Missing command: $fcitx5_remote" >&2; exit 1; }
fi
"$python_bin" -c 'import yaml' || { echo 'Install python3-yaml first.' >&2; exit 1; }
[[ -f "$rime_dir/rime_ice.schema.yaml" ]] || {
  echo "Missing Rime Ice schema: $rime_dir/rime_ice.schema.yaml" >&2
  echo 'Install Rime Ice for Fcitx5 first, then run this script again.' >&2
  exit 1
}

build() {
  rime_deployer --build "$rime_dir" "$shared_dir" "$rime_dir/build"
}

mkdir -p "$rime_dir"
if [[ ! -f "$rime_dir/build/default.yaml" || ! -f "$rime_dir/build/rime_ice.schema.yaml" ]]; then
  echo 'No compiled Rime Ice configuration found; running initial deployment.'
  build || { echo 'Initial deployment failed.' >&2; exit 1; }
fi

"$python_bin" - "$rime_dir" "$set_default" "$english" "$script_dir" "$wordlist" <<'PY'
import datetime
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml

root = Path(sys.argv[1])
set_default = sys.argv[2] == '1'
english = sys.argv[3] == '1'
source = Path(sys.argv[4])
wordlist = Path(sys.argv[5])

SCHEMA = 'rime_ice'
ENGLISH = 'xense_english_words'
ENGLISH_TRANSLATOR = f'table_translator@{ENGLISH}'
CHINESE = 'xense_common_phrases'
CHINESE_TRANSLATOR = f'table_translator@{CHINESE}'


def load_mapping(path):
    data = yaml.safe_load(path.read_text()) if path.exists() else None
    data = data or {}
    if not isinstance(data, dict):
        sys.exit(f'{path} must be a YAML mapping; no files changed.')
    patch = data.setdefault('patch', {})
    if not isinstance(patch, dict):
        sys.exit(f'patch in {path} must be a YAML mapping; no files changed.')
    return data, patch


def write_atomic(path, text, mode=0o644):
    fd, temporary = tempfile.mkstemp(prefix='.xense-terms-', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(path, data):
    rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if path.exists() and path.read_text() == rendered:
        print(f'Unchanged: {path}', flush=True)
        return
    if path.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = path.with_name(path.name + '.bak-' + stamp)
        shutil.copy2(path, backup)
        print(f'Backup: {backup}', flush=True)
    fd, temporary = tempfile.mkstemp(prefix='.xense-terms-', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(rendered)
        if path.exists():
            shutil.copymode(path, temporary)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Updated: {path}', flush=True)


def dependency_schema(schema_id, name):
    return {
        'schema': {'schema_id': schema_id, 'name': name, 'version': '1'},
        'engine': {
            'processors': ['speller', 'selector', 'express_editor'],
            'segmentors': ['abc_segmentor'],
            'translators': ['table_translator'],
        },
        'speller': {'alphabet': 'zyxwvutsrqponmlkjihgfedcba'},
        'translator': {'dictionary': schema_id},
    }


def english_dictionary():
    # Built-in entries fix capitalization and aliases. The optional system list
    # contributes one spelling per remaining lowercase code.
    entries, seen = [], set()
    for line in (source / 'english/words.txt').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        text, _, code = line.partition('\t')
        code = code.strip() or re.sub('[^a-z]', '', text.lower())
        if not text.strip() or not re.fullmatch('[a-z]+', code) or code in seen:
            sys.exit(f'Invalid or duplicate English code: {code}; no files changed.')
        entries.append((text.strip(), code))
        seen.add(code)
    system = {}
    if wordlist.is_file():
        for word in wordlist.read_text(errors='ignore').split():
            if re.fullmatch('[A-Za-z]{2,}', word):
                code = word.lower()
                if code not in seen and (code not in system or word == code):
                    system[code] = word
    else:
        print(f'Word list not found: {wordlist}; only built-in English words are enabled.', flush=True)
    entries += [(word, code) for code, word in system.items()]
    header = ('# Generated by rime-simplified-deploy; edit english/words.txt instead.\n'
              f'---\nname: {ENGLISH}\nversion: "1"\nsort: original\n...\n\n')
    return header + ''.join(f'{text}\t{code}\n' for text, code in entries), len(entries)


def chinese_dictionary():
    lines, seen_codes = [], set()
    for line in (source / 'chinese/phrases.tsv').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if (len(fields) != 2 or not fields[0].strip() or
                not re.fullmatch('[a-z]+', fields[1]) or fields[1] in seen_codes):
            sys.exit(f'Invalid or duplicate Chinese entry: {line}; no files changed.')
        seen_codes.add(fields[1])
        lines.append(line)
    header = ('# Generated by rime-simplified-deploy; edit chinese/phrases.tsv instead.\n'
              f'---\nname: {CHINESE}\nversion: "1"\nsort: original\n...\n\n')
    return header + '\n'.join(lines) + '\n', len(lines)


def owned_append(patch, key, owned):
    value = patch.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        sys.exit(f'Unsupported {key} configuration; no files changed.')
    return [item for item in value if item not in owned]


# Validate the effective base configuration before writing anything.
compiled = yaml.safe_load((root / f'build/{SCHEMA}.schema.yaml').read_text()) or {}
defaults = yaml.safe_load((root / 'build/default.yaml').read_text()) or {}
enabled = [item.get('schema') for item in defaults.get('schema_list', []) if isinstance(item, dict)]

default_target = root / 'default.custom.yaml'
default_data = None
if set_default:
    default_data, default_patch = load_mapping(default_target)
    schema_list = default_patch.get('schema_list')
    if schema_list is None:
        schema_list = [{'schema': name} for name in enabled]
    if not isinstance(schema_list, list) or not all(isinstance(item, dict) for item in schema_list):
        sys.exit('Unsupported schema_list in default.custom.yaml; no files changed.')
    default_patch['schema_list'] = [{'schema': SCHEMA}] + [
        item for item in schema_list if item.get('schema') != SCHEMA]
elif SCHEMA not in enabled:
    sys.exit(f'{SCHEMA} is not enabled. Re-run with --set-default, or add it to '
             'schema_list in default.custom.yaml and deploy first.')

target = root / f'{SCHEMA}.custom.yaml'
data, patch = load_mapping(target)
base_translators = (compiled.get('engine') or {}).get('translators')
base_dependencies = (compiled.get('schema') or {}).get('dependencies') or []
if (not isinstance(base_translators, list) or
        not all(isinstance(item, str) for item in base_translators)):
    sys.exit('Unsupported effective engine/translators configuration; no files changed.')
if (not isinstance(base_dependencies, list) or
        not all(isinstance(item, str) for item in base_dependencies)):
    sys.exit('Unsupported effective schema/dependencies configuration; no files changed.')
translators = owned_append(
    patch, 'engine/translators/+',
    {ENGLISH_TRANSLATOR, CHINESE_TRANSLATOR})
dependencies = owned_append(
    patch, 'schema/dependencies/+',
    {ENGLISH, CHINESE})

if english:
    translators.append(ENGLISH_TRANSLATOR)
    dependencies.append(ENGLISH)
    patch[ENGLISH] = {
        'dictionary': ENGLISH,
        'enable_completion': False,
        'enable_sentence': False,
        'enable_user_dict': False,
        'enable_encoder': False,
        # Keep exact English terms behind valid Chinese pinyin.
        'initial_quality': 0,
    }
    english_dict, english_count = english_dictionary()
else:
    patch.pop(ENGLISH, None)
    english_dict, english_count = None, 0

translators.append(CHINESE_TRANSLATOR)
dependencies.append(CHINESE)
patch['engine/translators/+'] = translators
patch['schema/dependencies/+'] = dependencies
patch[CHINESE] = {
    'dictionary': CHINESE,
    'enable_completion': False,
    'enable_sentence': False,
    'enable_user_dict': False,
    # Rime Ice's primary translator remains higher at 1.2.
    'initial_quality': 1,
}
chinese_dict, chinese_count = chinese_dictionary()

write_atomic(root / f'{CHINESE}.dict.yaml', chinese_dict)
write_atomic(root / f'{CHINESE}.schema.yaml', yaml.safe_dump(
    dependency_schema(CHINESE, 'Xense 常用中文词组'), allow_unicode=True, sort_keys=False))
print(f'Chinese supplemental phrases: {chinese_count}', flush=True)
if english:
    write_atomic(root / f'{ENGLISH}.dict.yaml', english_dict)
    write_atomic(root / f'{ENGLISH}.schema.yaml', yaml.safe_dump(
        dependency_schema(ENGLISH, 'Xense English Words'), allow_unicode=True, sort_keys=False))
    print(f'English words: {english_count}', flush=True)
if default_data is not None:
    save(default_target, default_data)
save(target, data)
PY

if ! build; then
  echo 'Deployment failed. Backup paths are printed above; see README.md for recovery.' >&2
  exit 1
fi
"$python_bin" - "$rime_dir/build" "$english" <<'PY'
from pathlib import Path
import sys

import yaml

build, english = Path(sys.argv[1]), sys.argv[2] == '1'
schema = yaml.safe_load((build / 'rime_ice.schema.yaml').read_text())
translators = schema['engine']['translators']
dependencies = schema['schema'].get('dependencies', [])
english_translator = 'table_translator@xense_english_words'
assert (english_translator in translators) == english, 'English translator state was not deployed'
assert ('xense_english_words' in dependencies) == english, 'English dependency state was not deployed'
assert not english or (build / 'xense_english_words.table.bin').exists(), 'English dictionary was not compiled'
assert 'table_translator@xense_common_phrases' in translators, 'Chinese translator missing'
assert 'xense_common_phrases' in dependencies, 'Chinese dependency missing'
assert (build / 'xense_common_phrases.table.bin').exists(), 'Chinese phrases were not compiled'
print('Compiled Rime Ice configuration verified.')
PY

if [[ $reload -eq 0 ]]; then
  echo 'Deployment complete. Reload Fcitx5 before testing the new candidates.'
  exit 0
fi

if ! "$fcitx5_remote" -r; then
  echo 'Configuration deployed, but Fcitx5 could not be reloaded. See README.md.' >&2
  exit 1
fi
for attempt in {1..5}; do
  current="$($fcitx5_remote -n 2>/dev/null || true)"
  if [[ "$current" == rime ]]; then
    echo 'Rime Ice terminology deployed and Fcitx5 reloaded.'
    exit 0
  fi
  sleep 1
done
echo 'Configuration deployed and Fcitx5 reloaded; select Rime before testing candidates.'
