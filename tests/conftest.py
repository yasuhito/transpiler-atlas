import json
import os
import pickle
import signal
import subprocess
import sys

import pytest


@pytest.fixture
def bounded_qcec():
    """Strict repository checker in a child with a diagnostic 60-second wall cap."""

    def check(original, native, initial, final):
        code = (
            "import json,pickle,sys;import atlas;"
            "args=pickle.load(sys.stdin.buffer);"
            "print(json.dumps(atlas.check_equivalence(*args)))"
        )
        with subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as child:
            try:
                stdout, stderr = child.communicate(
                    pickle.dumps((original, native, initial, final)), timeout=60
                )
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                pytest.fail("QCEC incomplete: external diagnostic wall limit, not non-equivalence")
            assert child.returncode == 0, stderr.decode()
        return json.loads(stdout)

    return check
