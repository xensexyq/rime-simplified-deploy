"""Real librime smoke test; uses only temporary data, never restarts IBus."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]


class Traits(C.Structure):
    _fields_ = [('data_size', C.c_int)] + [(n, C.c_char_p) for n in (
        'shared_data_dir', 'user_data_dir', 'distribution_name', 'distribution_code_name',
        'distribution_version', 'app_name')] + [('modules', C.c_void_p), ('min_log_level', C.c_int),
        ('log_dir', C.c_char_p), ('prebuilt_data_dir', C.c_char_p), ('staging_dir', C.c_char_p)]


class Candidate(C.Structure):
    _fields_ = [('text', C.c_char_p), ('comment', C.c_char_p), ('reserved', C.c_void_p)]


class Iterator(C.Structure):
    _fields_ = [('ptr', C.c_void_p), ('index', C.c_int), ('candidate', Candidate)]


@unittest.skipUnless(shutil.which('rime_deployer') and shutil.which('ibus') and
                     Path('/usr/share/rime-data/luna_pinyin_simp.schema.yaml').exists() and
                     ctypes.util.find_library('rime'), 'requires IBus Rime and system schema data')
class CandidateTests(unittest.TestCase):
    def test_real_candidates(self):
        with tempfile.TemporaryDirectory(prefix='rime-candidates-') as tmp:
            root = Path(tmp)
            result = subprocess.run(['bash', str(PACKAGE / 'deploy.sh'), '--no-restart', '--set-default'],
                                    env=dict(os.environ, RIME_USER_DIR=tmp,
                                             RIME_SHARED_DIR='/usr/share/rime-data'),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lib = C.CDLL(ctypes.util.find_library('rime'))
            for name, args, returns in (
                ('RimeSetup', [C.POINTER(Traits)], None),
                ('RimeInitialize', [C.POINTER(Traits)], None),
                ('RimeFinalize', [], None),
                ('RimeCreateSession', [], C.c_size_t),
                ('RimeDestroySession', [C.c_size_t], C.c_int),
                ('RimeSelectSchema', [C.c_size_t, C.c_char_p], C.c_int),
                ('RimeClearComposition', [C.c_size_t], None),
                ('RimeSimulateKeySequence', [C.c_size_t, C.c_char_p], C.c_int),
                ('RimeCandidateListBegin', [C.c_size_t, C.POINTER(Iterator)], C.c_int),
                ('RimeCandidateListNext', [C.POINTER(Iterator)], C.c_int),
                ('RimeCandidateListEnd', [C.POINTER(Iterator)], None),
            ):
                function = getattr(lib, name)
                function.argtypes, function.restype = args, returns
            traits = Traits()
            traits.data_size = C.sizeof(Traits) - C.sizeof(C.c_int)
            traits.shared_data_dir = b'/usr/share/rime-data'
            traits.user_data_dir = tmp.encode()
            traits.staging_dir = str(root / 'build').encode()
            traits.prebuilt_data_dir = b'/usr/share/rime-data/build'
            traits.app_name = b'rime.candidate_test'
            traits.min_log_level = 3
            traits.log_dir = tmp.encode()
            lib.RimeSetup(C.byref(traits))
            lib.RimeInitialize(C.byref(traits))
            session = lib.RimeCreateSession()
            try:
                self.assertTrue(lib.RimeSelectSchema(session, b'luna_pinyin_simp'))
                cases = {'meiwenti': '没问题', 'huiyijiyao': '会议纪要',
                         'jushenzhineng': '具身智能', 'rengongzhineng': '人工智能',
                         'ruanjiankaifa': '软件开发', 'asap': 'ASAP', 'fyi': 'FYI',
                         'lgtm': 'LGTM', 'brb': 'BRB', 'tldr': 'TLDR',
                         'ipvfour': 'IPv4', 'ipvsix': 'IPv6', 'rostwo': 'ROS2',
                         'btob': 'B2B', 'github': 'GitHub', 'women': '我们',
                         'nihao': '你好', 'zhongwen': '中文'}
                for code, expected in cases.items():
                    with self.subTest(code=code):
                        lib.RimeClearComposition(session)
                        lib.RimeSimulateKeySequence(session, code.encode())
                        iterator, candidates = Iterator(), []
                        if lib.RimeCandidateListBegin(session, C.byref(iterator)):
                            try:
                                while len(candidates) < 8 and lib.RimeCandidateListNext(C.byref(iterator)):
                                    candidates.append(iterator.candidate.text.decode())
                            finally:
                                lib.RimeCandidateListEnd(C.byref(iterator))
                        print(f'{code}: {" | ".join(candidates[:5])}')
                        self.assertIn(expected, candidates)
                        if code in ('women', 'nihao', 'zhongwen'):
                            self.assertEqual(candidates[0], expected)
            finally:
                lib.RimeDestroySession(session)
                lib.RimeFinalize()


if __name__ == '__main__':
    unittest.main()
