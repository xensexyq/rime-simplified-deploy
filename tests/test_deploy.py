"""Isolated tests for Fcitx5 + Rime Ice deployment."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml

PACKAGE = Path(__file__).resolve().parents[1]

# Minimal stand-in for rime_deployer: applies slash-delimited patch keys from
# user custom files to shared/user schemas and creates dependency table markers.
FAKE_DEPLOYER = textwrap.dedent('''\
    #!{python}
    import sys, yaml
    from pathlib import Path
    assert sys.argv[1] == '--build'
    user, shared, build = map(Path, sys.argv[2:5])
    build.mkdir(parents=True, exist_ok=True)
    sources = list(shared.glob('*.yaml')) + list(user.glob('*.schema.yaml'))
    for source in sources:
        data = yaml.safe_load(source.read_text()) or {{}}
        stem = source.name.split('.')[0]
        custom = user / (stem + '.custom.yaml')
        if custom.exists():
            for key, value in (yaml.safe_load(custom.read_text()) or {{}}).get('patch', {{}}).items():
                parts = key.split('/')
                node = data
                if parts[-1] == '+':
                    for part in parts[:-2]:
                        node = node.setdefault(part, {{}})
                    target = parts[-2]
                    current = node.setdefault(target, [])
                    assert isinstance(current, list) and isinstance(value, list)
                    node[target] = current + value
                else:
                    for part in parts[:-1]:
                        node = node.setdefault(part, {{}})
                    node[parts[-1]] = value
        (build / source.name).write_text(yaml.safe_dump(data, allow_unicode=True))
        for dependency in (data.get('schema') or {{}}).get('dependencies') or []:
            if (user / (dependency + '.schema.yaml')).exists():
                (build / (dependency + '.table.bin')).write_text('')
''')

RIME_SCHEMA = {
    'schema': {
        'schema_id': 'rime_ice',
        'name': '雾凇拼音',
        'dependencies': ['melt_eng', 'radical_pinyin'],
    },
    'engine': {
        'translators': [
            'punct_translator',
            'script_translator',
            'table_translator@melt_eng',
        ],
        'filters': ['simplifier@traditionalize', 'uniquifier'],
    },
    'switches': [
        {'name': 'ascii_mode', 'states': ['中', 'Ａ']},
        {'name': 'traditionalization', 'states': ['简', '繁']},
    ],
    'traditionalize': {'option_name': 'traditionalization', 'opencc_config': 's2t.json'},
}
SHARED_DEFAULT = {
    'schema_list': [{'schema': 'rime_ice'}, {'schema': 'double_pinyin_flypy'}],
}


class DeployTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rime-tests-')
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.user = base / 'user dir/rime'
        self.shared = base / 'shared'
        self.user.mkdir(parents=True)
        self.shared.mkdir()
        (self.user / 'rime_ice.schema.yaml').write_text(
            yaml.safe_dump(RIME_SCHEMA, allow_unicode=True))
        (self.shared / 'default.yaml').write_text(
            yaml.safe_dump(SHARED_DEFAULT, allow_unicode=True))

        bin_dir = base / 'bin'
        bin_dir.mkdir()
        deployer = bin_dir / 'rime_deployer'
        deployer.write_text(FAKE_DEPLOYER.format(python=sys.executable))
        self.fcitx_log = base / 'fcitx.log'
        fcitx = bin_dir / 'fcitx5-remote'
        fcitx.write_text(textwrap.dedent('''\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$FCITX_LOG"
            [ "$1" = "-n" ] && printf '%s\\n' rime
            exit 0
        '''))
        for tool in (deployer, fcitx):
            tool.chmod(0o755)

        wordlist = base / 'words'
        wordlist.write_text("hello\nHello\nPolish\nlinux\nit's\na\nmake\n")
        self.env = dict(
            os.environ,
            PATH=f'{bin_dir}:{os.environ["PATH"]}',
            RIME_USER_DIR=str(self.user),
            RIME_SHARED_DIR=str(self.shared),
            RIME_PYTHON=sys.executable,
            RIME_ENGLISH_WORDLIST=str(wordlist),
            FCITX_LOG=str(self.fcitx_log),
        )

    def run_deploy(self, *args, check=True):
        result = subprocess.run(
            ['bash', str(PACKAGE / 'deploy.sh'), *args],
            env=self.env,
            capture_output=True,
            text=True,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def load(self, path):
        return yaml.safe_load((self.user / path).read_text())

    def compiled(self):
        return self.load('build/rime_ice.schema.yaml')

    def english_entries(self):
        body = (self.user / 'xense_english_words.dict.yaml').read_text().split('...\n', 1)[1]
        return [tuple(line.split('\t')) for line in body.splitlines() if line]

    def test_fresh_install_preserves_rime_ice_behavior(self):
        output = self.run_deploy('--no-reload').stdout
        self.assertIn('initial deployment', output)
        self.assertIn('Compiled Rime Ice configuration verified', output)
        patch = self.load('rime_ice.custom.yaml')['patch']
        self.assertNotIn('switches', patch)
        self.assertNotIn('simplifier/option_name', patch)
        self.assertEqual(
            patch['engine/translators/+'][-2:],
            ['table_translator@xense_english_words',
             'table_translator@xense_common_phrases'],
        )
        self.assertEqual(
            patch['schema/dependencies/+'][-2:],
            ['xense_english_words', 'xense_common_phrases'],
        )
        compiled = self.compiled()
        self.assertEqual(
            compiled['traditionalize'],
            {'option_name': 'traditionalization', 'opencc_config': 's2t.json'},
        )
        self.assertEqual(compiled['switches'], RIME_SCHEMA['switches'])

    def test_existing_config_is_preserved_backed_up_and_idempotent(self):
        custom = self.user / 'rime_ice.custom.yaml'
        custom.write_text(yaml.safe_dump({'patch': {
            'schema/name': '我的雾凇',
            'engine/translators/+': ['table_translator@my_terms'],
            'key_binder/bindings/+': [
                {'when': 'has_menu', 'accept': 'comma', 'send': 'Page_Up'},
            ],
        }}, allow_unicode=True))
        original = custom.read_text()
        self.run_deploy('--no-reload')
        patch = self.load('rime_ice.custom.yaml')['patch']
        self.assertEqual(patch['schema/name'], '我的雾凇')
        self.assertEqual(patch['key_binder/bindings/+'][0]['accept'], 'comma')
        self.assertEqual(
            patch['engine/translators/+'][0],
            'table_translator@my_terms')
        backups = list(self.user.glob('rime_ice.custom.yaml.bak-*'))
        self.assertEqual([backup.read_text() for backup in backups], [original])
        first = custom.read_text()
        self.run_deploy('--no-reload')
        self.assertEqual(custom.read_text(), first)
        self.assertEqual(len(list(self.user.glob('rime_ice.custom.yaml.bak-*'))), 1)

    def test_english_words_enabled(self):
        self.run_deploy('--no-reload')
        entries = self.english_entries()
        self.assertIn(('GitHub', 'github'), entries)
        self.assertIn(('Node.js', 'nodejs'), entries)
        self.assertIn(('hello', 'hello'), entries)
        self.assertIn(('Polish', 'polish'), entries)
        self.assertNotIn(('Hello', 'hello'), entries)
        self.assertNotIn(('linux', 'linux'), entries)
        compiled = self.compiled()
        self.assertIn(
            'table_translator@xense_english_words',
            compiled['engine']['translators'],
        )
        self.assertEqual(compiled['xense_english_words']['initial_quality'], 0)
        self.assertTrue((self.user / 'build/xense_english_words.table.bin').exists())

    def test_no_english_removes_previous_setup(self):
        self.run_deploy('--no-reload')
        self.run_deploy('--no-reload', '--no-english')
        patch = self.load('rime_ice.custom.yaml')['patch']
        self.assertNotIn('xense_english_words', patch)
        self.assertNotIn(
            'table_translator@xense_english_words',
            patch['engine/translators/+'],
        )
        self.assertNotIn('xense_english_words', patch['schema/dependencies/+'])
        self.assertNotIn(
            'table_translator@xense_english_words',
            self.compiled()['engine']['translators'],
        )
        self.assertIn(
            'table_translator@xense_common_phrases',
            self.compiled()['engine']['translators'],
        )

    def test_missing_wordlist_uses_builtin_words(self):
        self.env['RIME_ENGLISH_WORDLIST'] = str(self.shared / 'missing')
        output = self.run_deploy('--no-reload').stdout
        self.assertIn('only built-in English words', output)
        entries = self.english_entries()
        self.assertIn(('GitHub', 'github'), entries)
        self.assertIn(('LeRobot', 'lerobot'), entries)
        self.assertNotIn(('hello', 'hello'), entries)

    def test_chinese_phrases_and_domain_terms(self):
        self.run_deploy('--no-reload')
        dictionary = (self.user / 'xense_common_phrases.dict.yaml').read_text()
        for entry in ('没问题\tmeiwenti', '会议纪要\thuiyijiyao', '手眼标定\tshouyanbiaoding'):
            self.assertIn(entry, dictionary)
        entries = self.english_entries()
        for entry in [('ROS2', 'rostwo'), ('LeRobot', 'lerobot'),
                      ('Xense', 'xense'), ('TacCap', 'taccap')]:
            self.assertIn(entry, entries)
        self.assertTrue((self.user / 'build/xense_common_phrases.table.bin').exists())
        self.assertFalse(self.compiled()['xense_common_phrases']['enable_completion'])

    def test_set_default_moves_rime_ice_first(self):
        (self.shared / 'default.yaml').write_text(yaml.safe_dump({
            'schema_list': [
                {'schema': 'double_pinyin_flypy'},
                {'schema': 'rime_ice'},
            ],
        }))
        self.run_deploy('--no-reload', '--set-default')
        schemas = [
            item['schema']
            for item in self.load('default.custom.yaml')['patch']['schema_list']
        ]
        self.assertEqual(schemas, ['rime_ice', 'double_pinyin_flypy'])

    def test_disabled_schema_fails_without_changes(self):
        (self.shared / 'default.yaml').write_text(yaml.safe_dump({
            'schema_list': [{'schema': 'double_pinyin_flypy'}],
        }))
        result = self.run_deploy('--no-reload', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--set-default', result.stderr)
        self.assertFalse((self.user / 'rime_ice.custom.yaml').exists())
        self.assertFalse((self.user / 'xense_common_phrases.dict.yaml').exists())

    def test_invalid_translators_fail_without_changes(self):
        custom = self.user / 'rime_ice.custom.yaml'
        custom.write_text('patch:\n  engine/translators: oops\n')
        result = self.run_deploy('--no-reload', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            custom.read_text(),
            'patch:\n  engine/translators: oops\n',
        )
        self.assertFalse((self.user / 'xense_common_phrases.dict.yaml').exists())

    def test_reload_uses_fcitx5_remote(self):
        output = self.run_deploy().stdout
        self.assertIn('Fcitx5 reloaded', output)
        self.assertEqual(self.fcitx_log.read_text().splitlines(), ['-r', '-n'])

    def test_bad_arguments(self):
        self.assertEqual(self.run_deploy('--bogus', check=False).returncode, 2)
        help_result = self.run_deploy('--help')
        self.assertIn('--no-reload', help_result.stdout)
        self.assertIn('--set-default', help_result.stdout)


if __name__ == '__main__':
    unittest.main()
