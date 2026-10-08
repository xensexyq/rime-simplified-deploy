"""Real librime smoke test using a temporary copy of an installed Rime Ice tree."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
DEFAULT_RIME_ICE = Path.home() / '.local/share/fcitx5/rime'
RIME_ICE_SOURCE = Path(
    os.environ.get('RIME_ICE_TEST_DIR', DEFAULT_RIME_ICE)
).expanduser()


class Traits(C.Structure):
    _fields_ = [('data_size', C.c_int)] + [(name, C.c_char_p) for name in (
        'shared_data_dir',
        'user_data_dir',
        'distribution_name',
        'distribution_code_name',
        'distribution_version',
        'app_name',
    )] + [
        ('modules', C.c_void_p),
        ('min_log_level', C.c_int),
        ('log_dir', C.c_char_p),
        ('prebuilt_data_dir', C.c_char_p),
        ('staging_dir', C.c_char_p),
    ]


class Candidate(C.Structure):
    _fields_ = [
        ('text', C.c_char_p),
        ('comment', C.c_char_p),
        ('reserved', C.c_void_p),
    ]


class Iterator(C.Structure):
    _fields_ = [
        ('ptr', C.c_void_p),
        ('index', C.c_int),
        ('candidate', Candidate),
    ]


def copy_ignore(_directory, names):
    ignored = {'build', 'sync', 'installation.yaml', 'user.yaml'}
    return {
        name for name in names
        if name in ignored or name.endswith('.userdb') or '.bak-' in name
    }


@unittest.skipUnless(
    shutil.which('rime_deployer')
    and (RIME_ICE_SOURCE / 'rime_ice.schema.yaml').exists()
    and ctypes.util.find_library('rime'),
    'requires librime and an installed Rime Ice tree',
)
class CandidateTests(unittest.TestCase):
    def test_real_rime_ice_candidates(self):
        with tempfile.TemporaryDirectory(prefix='rime-ice-candidates-') as tmp:
            user = Path(tmp) / 'rime'
            shutil.copytree(RIME_ICE_SOURCE, user, ignore=copy_ignore)
            result = subprocess.run(
                ['bash', str(PACKAGE / 'deploy.sh'), '--no-reload', '--set-default'],
                env=dict(
                    os.environ,
                    RIME_USER_DIR=str(user),
                    RIME_SHARED_DIR='/usr/share/rime-data',
                ),
                capture_output=True,
                text=True,
            )
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
                function.argtypes = args
                function.restype = returns

            traits = Traits()
            traits.data_size = C.sizeof(Traits) - C.sizeof(C.c_int)
            traits.shared_data_dir = b'/usr/share/rime-data'
            traits.user_data_dir = str(user).encode()
            traits.staging_dir = str(user / 'build').encode()
            traits.prebuilt_data_dir = b'/usr/share/rime-data/build'
            traits.app_name = b'rime.rime_ice_candidate_test'
            traits.min_log_level = 3
            traits.log_dir = tmp.encode()
            lib.RimeSetup(C.byref(traits))
            lib.RimeInitialize(C.byref(traits))
            session = lib.RimeCreateSession()
            try:
                self.assertTrue(lib.RimeSelectSchema(session, b'rime_ice'))
                cases = {
                    'meiwenti': '没问题',
                    'shouyanbiaoding': '手眼标定',
                    'lerobot': 'LeRobot',
                    'smolvla': 'SmolVLA',
                    'xense': 'Xense',
                    'taccap': 'TacCap',
                    'rostwo': 'ROS2',
                }
                for code, expected in cases.items():
                    with self.subTest(code=code):
                        lib.RimeClearComposition(session)
                        lib.RimeSimulateKeySequence(session, code.encode())
                        iterator, candidates = Iterator(), []
                        if lib.RimeCandidateListBegin(session, C.byref(iterator)):
                            try:
                                while len(candidates) < 12 and lib.RimeCandidateListNext(
                                        C.byref(iterator)):
                                    candidates.append(iterator.candidate.text.decode())
                            finally:
                                lib.RimeCandidateListEnd(C.byref(iterator))
                        print(f'{code}: {" | ".join(candidates[:5])}')
                        self.assertIn(expected, candidates)

                lib.RimeClearComposition(session)
                lib.RimeSimulateKeySequence(session, b'women')
                iterator, candidates = Iterator(), []
                if lib.RimeCandidateListBegin(session, C.byref(iterator)):
                    try:
                        while len(candidates) < 5 and lib.RimeCandidateListNext(
                                C.byref(iterator)):
                            candidates.append(iterator.candidate.text.decode())
                    finally:
                        lib.RimeCandidateListEnd(C.byref(iterator))
                self.assertEqual(candidates[0], '我们')
            finally:
                lib.RimeDestroySession(session)
                lib.RimeFinalize()


if __name__ == '__main__':
    unittest.main()
