"""Isolated tests for deploy.sh: fake rime_deployer/ibus, temporary Rime directories."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml

PACKAGE = Path(__file__).resolve().parents[1]

# Minimal stand-in for rime_deployer: applies "patch" (with a/b key paths) from
# <name>.custom.yaml onto the shared <name>.yaml / <name>.schema.yaml.
FAKE_DEPLOYER = textwrap.dedent('''\
    #!{python}
    import sys, yaml
    from pathlib import Path
    assert sys.argv[1] == '--build'
    user, shared, build = map(Path, sys.argv[2:5])
    build.mkdir(parents=True, exist_ok=True)
    for source in shared.glob('*.yaml'):
        data = yaml.safe_load(source.read_text()) or {{}}
        stem = source.name.split('.')[0]
        custom = user / (stem + '.custom.yaml')
        if custom.exists():
            for key, value in (yaml.safe_load(custom.read_text()) or {{}}).get('patch', {{}}).items():
                node, parts = data, key.split('/')
                for part in parts[:-1]:
                    node = node.setdefault(part, {{}})
                node[parts[-1]] = value
        (build / source.name).write_text(yaml.safe_dump(data, allow_unicode=True))
        for dependency in (data.get('schema') or {{}}).get('dependencies') or []:
            if (user / (dependency + '.schema.yaml')).exists():
                (build / (dependency + '.table.bin')).write_text('')
''')

SHARED_SCHEMA = {
    'schema': {'schema_id': 'luna_pinyin_simp', 'name': '朙月拼音·简化字', 'dependencies': ['stroke']},
    'engine': {'translators': ['punct_translator', 'script_translator']},
    'switches': [
        {'name': 'ascii_mode', 'reset': 0, 'states': ['中文', '西文']},
        {'name': 'zh_simp', 'reset': 1, 'states': ['漢字', '汉字']},
    ],
    'simplifier': {'option_name': 'zh_simp'},
}
SHARED_DEFAULT = {'schema_list': [{'schema': 'luna_pinyin'}, {'schema': 'luna_pinyin_simp'}]}


class DeployTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='rime-tests-')
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.user = base / 'user dir/rime'
        self.shared = base / 'shared'
        self.shared.mkdir()
        (self.shared / 'luna_pinyin_simp.schema.yaml').write_text(yaml.safe_dump(SHARED_SCHEMA, allow_unicode=True))
        (self.shared / 'default.yaml').write_text(yaml.safe_dump(SHARED_DEFAULT))
        bin_dir = base / 'bin'
        bin_dir.mkdir()
        deployer = bin_dir / 'rime_deployer'
        deployer.write_text(FAKE_DEPLOYER.format(python=sys.executable))
        ibus = bin_dir / 'ibus'
        ibus.write_text('#!/bin/sh\n[ "$1 $2" = "engine rime" ] && exit 0\n[ "$1" = engine ] && echo rime\nexit 0\n')
        for tool in (deployer, ibus):
            tool.chmod(0o755)
        wordlist = base / 'words'
        wordlist.write_text("hello\nHello\nPolish\nlinux\nit's\na\nmake\n")
        self.env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', RIME_USER_DIR=str(self.user),
                        RIME_SHARED_DIR=str(self.shared), RIME_PYTHON=sys.executable,
                        RIME_ENGLISH_WORDLIST=str(wordlist))

    def run_deploy(self, *args, check=True):
        result = subprocess.run(['bash', str(PACKAGE / 'deploy.sh'), *args], env=self.env,
                                capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def load(self, path):
        return yaml.safe_load((self.user / path).read_text())

    def compiled(self):
        return self.load('build/luna_pinyin_simp.schema.yaml')

    def test_fresh_install_creates_config(self):
        output = self.run_deploy().stdout
        self.assertIn('initial deployment', output)
        self.assertIn('Rime is running', output)
        patch = self.load('luna_pinyin_simp.custom.yaml')['patch']
        self.assertEqual([s['name'] for s in patch['switches']], ['ascii_mode', 'simplified_output'])
        self.assertEqual(self.compiled()['simplifier'], {'option_name': 'simplified_output', 'opencc_config': 't2s.json'})
        self.assertEqual(list(self.user.glob('*.bak-*')), [])

    def test_existing_config_is_preserved_backed_up_and_idempotent(self):
        self.user.mkdir(parents=True)
        custom = self.user / 'luna_pinyin_simp.custom.yaml'
        custom.write_text(yaml.safe_dump({'patch': {
            'schema/name': '拼音（简体）',
            'switches': [{'name': 'full_shape'}, {'name': 'simplified_output', 'reset': 0}],
            'simplifier/option_name': ''}}, allow_unicode=True))
        original = custom.read_text()
        self.run_deploy('--no-restart')
        patch = self.load('luna_pinyin_simp.custom.yaml')['patch']
        self.assertEqual(patch['schema/name'], '拼音（简体）')
        self.assertEqual(patch['switches'], [{'name': 'full_shape'}, {'name': 'simplified_output', 'reset': 1}])
        backups = list(self.user.glob('luna_pinyin_simp.custom.yaml.bak-*'))
        self.assertEqual([b.read_text() for b in backups], [original])
        first = custom.read_text()
        self.run_deploy('--no-restart')
        self.assertEqual(custom.read_text(), first)

    def english_entries(self):
        lines = (self.user / 'english_words.dict.yaml').read_text().split('...\n', 1)[1].split('\n')
        return [tuple(line.split('\t')) for line in lines if line]

    def test_english_words_enabled_and_idempotent(self):
        self.run_deploy('--no-restart')
        entries = self.english_entries()
        self.assertIn(('GitHub', 'github'), entries)
        self.assertIn(('Node.js', 'nodejs'), entries)
        self.assertIn(('hello', 'hello'), entries)
        self.assertIn(('Polish', 'polish'), entries)
        self.assertIn(('make', 'make'), entries)
        self.assertNotIn(('Hello', 'hello'), entries)
        self.assertNotIn(('linux', 'linux'), entries)
        self.assertFalse({'a', "it's"} & {code for _, code in entries})
        self.assertTrue((self.user / 'english_words.schema.yaml').exists())
        compiled = self.compiled()
        self.assertEqual(compiled['engine']['translators'],
                         ['punct_translator', 'script_translator', 'table_translator@english_words'])
        self.assertEqual(compiled['schema']['dependencies'], ['stroke', 'english_words'])
        self.assertEqual(compiled['english_words']['initial_quality'], 0)
        custom = self.user / 'luna_pinyin_simp.custom.yaml'
        first = custom.read_text()
        self.run_deploy('--no-restart')
        self.assertEqual(custom.read_text(), first)

    def test_no_english_removes_previous_setup(self):
        self.run_deploy('--no-restart')
        self.run_deploy('--no-restart', '--no-english')
        patch = self.load('luna_pinyin_simp.custom.yaml')['patch']
        self.assertNotIn('english_words', patch)
        self.assertEqual(patch['engine/translators'], ['punct_translator', 'script_translator'])
        self.assertEqual(patch['schema/dependencies'], ['stroke'])
        self.assertNotIn('table_translator@english_words', self.compiled()['engine']['translators'])

    def test_missing_wordlist_uses_builtin_words(self):
        self.env['RIME_ENGLISH_WORDLIST'] = str(self.shared / 'missing')
        self.assertIn('only built-in', self.run_deploy('--no-restart').stdout)
        self.assertIn(('GitHub', 'github'), self.english_entries())
        self.assertNotIn(('hello', 'hello'), self.english_entries())

    def test_set_default_moves_schema_first(self):
        self.run_deploy('--no-restart', '--set-default')
        schemas = [s['schema'] for s in self.load('default.custom.yaml')['patch']['schema_list']]
        self.assertEqual(schemas, ['luna_pinyin_simp', 'luna_pinyin'])

    def test_disabled_schema_fails_without_changes(self):
        (self.shared / 'default.yaml').write_text(yaml.safe_dump({'schema_list': [{'schema': 'luna_pinyin'}]}))
        result = self.run_deploy('--no-restart', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--set-default', result.stderr)
        self.assertFalse((self.user / 'luna_pinyin_simp.custom.yaml').exists())

    def test_invalid_switches_fail_without_changes(self):
        self.user.mkdir(parents=True)
        custom = self.user / 'luna_pinyin_simp.custom.yaml'
        custom.write_text('patch:\n  switches: oops\n')
        result = self.run_deploy('--no-restart', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(custom.read_text(), 'patch:\n  switches: oops\n')
        self.assertEqual(list(self.user.glob('*.bak-*')), [])

    def test_bad_arguments(self):
        self.assertEqual(self.run_deploy('--bogus', check=False).returncode, 2)
        self.assertIn('--set-default', self.run_deploy('--help').stdout)


if __name__ == '__main__':
    unittest.main()
