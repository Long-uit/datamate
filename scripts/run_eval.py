import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

python_exe = Path(".venv/Scripts/python.exe")
output_file = Path("test_10question_after.txt")

cmd = [str(python_exe), "scripts/phase1_loop.py", "--limit", "10"]
print(f"Running: {' '.join(cmd)}", flush=True)

with open(output_file, "w", encoding="utf-8") as out_f:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )
    for line in proc.stdout:
        out_f.write(line)
        out_f.flush()
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass

    proc.wait()
    print(f"\nExited with code: {proc.returncode}", flush=True)
