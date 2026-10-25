"""Run installed console entry point away from source tree."""

import json
import os
import subprocess
import sysconfig
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="interleave-installed-") as folder:
    executable = str(
        Path(sysconfig.get_path("scripts"))
        / ("interleave.exe" if os.name == "nt" else "interleave")
    )
    path = Path(folder) / "history.json"
    path.write_text(
        json.dumps({"schema": 1, "model": "register", "initial": 0, "operations": []}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [executable, str(path)],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "linearizable" and report["witness"] == []
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "model": "register",
                "initial": 0,
                "operations": [
                    {
                        "id": "a",
                        "process": "a",
                        "kind": "cas",
                        "input": [0, 1],
                        "output": True,
                        "call": 0,
                        "return": 4,
                    },
                    {
                        "id": "b",
                        "process": "b",
                        "kind": "cas",
                        "input": [0, 2],
                        "output": True,
                        "call": 1,
                        "return": 5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [executable, str(path), "--minimize"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "nonlinearizable" and report["counterexample"]["one_minimal"]
    print("Installed console script outside source tree: passed")
