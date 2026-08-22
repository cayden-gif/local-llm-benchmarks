# Keep the benchmark site current without anyone touching it.
#
# Checks what Ollama has installed against what has already been measured,
# benchmarks anything new, rebuilds the pages and pushes. Git credentials are
# cached in Windows Credential Manager, so the push needs no terminal.
#
#   python update.py            check once and exit
#   python update.py --daemon   check every 24 hours
#   python update.py --force    rebuild and push even with nothing new
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = r"C:\Users\RNGAI\jarvis_env\Scripts\python.exe"
PY = VENV if os.path.exists(VENV) else sys.executable
RESULTS = os.path.join(HERE, "results.json")
LOG = os.path.join(HERE, "update.log")
DAY = 24 * 60 * 60


def say(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(cmd, timeout=None):
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as e:
        return 1, type(e).__name__ + " " + str(e)


def measured():
    try:
        with open(RESULTS, encoding="utf-8") as f:
            return set(json.load(f).get("models", {}).keys())
    except Exception:
        return set()


def installed():
    code, out = run(["ollama", "list"], timeout=60)
    if code != 0:
        say("could not list models: " + out.strip()[:120])
        return set()
    names = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        # A size of "-" means the model is cloud-hosted; benchmarking it would
        # measure someone else's datacentre, not this machine.
        if len(parts) >= 3 and parts[2] != "-":
            names.add(parts[0])
    return names


def check_once(force=False):
    have, want = measured(), installed()
    if not want:
        say("no local models visible - is Ollama running?")
        return False
    new = sorted(want - have)
    gone = sorted(have - want)
    if gone:
        say("note: " + str(len(gone)) + " measured model(s) no longer "
            "installed, keeping their results: " + ", ".join(gone[:4]))
    if not new and not force:
        say("nothing new (" + str(len(have)) + " models already measured)")
        return False

    for name in new:
        say("benchmarking " + name)
        code, out = run([PY, os.path.join(HERE, "bench.py"), "--only", name],
                        timeout=3600)
        if code != 0:
            say("  bench failed (" + str(code) + "): " + out.strip()[-160:])

    say("rebuilding site")
    code, out = run([PY, os.path.join(HERE, "build_site.py")], timeout=300)
    if code != 0:
        say("build failed: " + out.strip()[-200:])
        return False

    # docs/ is what GitHub Pages serves, so the built pages have to land there.
    for f in os.listdir(os.path.join(HERE, "site")):
        src = os.path.join(HERE, "site", f)
        dst = os.path.join(HERE, "docs", f)
        try:
            with open(src, "rb") as a, open(dst, "wb") as b:
                b.write(a.read())
        except OSError as e:
            say("could not copy " + f + ": " + type(e).__name__)

    code, out = run(["git", "add", "-A"], timeout=60)
    msg = ("Add " + ", ".join(new) if new else "Rebuild site")
    code, out = run(["git", "-c", "user.email=cayden@relativemarketinggroup.com",
                     "-c", "user.name=cayden-gif", "commit", "-m", msg],
                    timeout=60)
    if "nothing to commit" in out:
        say("no file changes to publish")
        return False
    code, out = run(["git", "push", "origin", "main"], timeout=180)
    if code != 0:
        say("push failed: " + out.strip()[-200:])
        return False
    say("published: " + msg)
    return True


def main():
    force = "--force" in sys.argv
    if "--daemon" not in sys.argv:
        return 0 if check_once(force) is not None else 1
    say("daemon start - checking every 24h")
    while True:
        try:
            check_once(force)
        except Exception as e:
            say("check raised " + type(e).__name__ + ": " + str(e)[:120])
        force = False
        time.sleep(DAY)


if __name__ == "__main__":
    sys.exit(main() or 0)
