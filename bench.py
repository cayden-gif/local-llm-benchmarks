# Measure how local models actually behave on a machine with no GPU.
#
# Every benchmark site tests CUDA cards. Almost nobody publishes "what happens
# on a normal laptop", which is exactly what someone wants to know before
# downloading a 16GB model. That gap is the whole point: this data is MEASURED
# here, so it cannot be scraped from anywhere else.
#
#   python bench.py --list           show installed models and sizes
#   python bench.py                  benchmark everything (slow, hours)
#   python bench.py --only qwen2.5   benchmark matching models only
import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.json")

# One short prompt and one longer one. Time-to-first-token is what makes a
# model feel slow; tokens/sec is what makes a long answer painful. Both matter
# and they are not the same measurement.
PROMPTS = [
    ("short", "Reply with exactly one word: hello", 40),
    ("medium", "Explain what a variable is in programming, in 3 sentences.", 220),
]
# A model that has not answered in this long is unusable on this hardware,
# which is itself a useful result rather than a failure.
TIMEOUT = 420


def post(path, payload, timeout=TIMEOUT):
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def installed():
    try:
        out = subprocess.check_output(["ollama", "list"], text=True,
                                      stderr=subprocess.DEVNULL)
    except Exception as e:
        print("could not run 'ollama list': " + type(e).__name__)
        return []
    models = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        name, size, unit = parts[0], parts[2], parts[3] if len(parts) > 3 else ""
        # Cloud-hosted entries have no local size and are not this machine's
        # problem - benchmarking them would measure someone else's datacentre.
        if size == "-":
            continue
        models.append({"name": name, "size": size + " " + unit})
    return models


def hardware():
    info = {"os": platform.platform(), "python": platform.python_version(),
            "cpu": platform.processor() or "unknown", "ram_gb": None,
            "gpu": "unknown"}
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
             "(Get-CimInstance Win32_Processor).Name;"
             "(Get-CimInstance Win32_VideoController).Name"],
            text=True, stderr=subprocess.DEVNULL, timeout=40)
        bits = [x.strip() for x in out.splitlines() if x.strip()]
        if bits:
            info["ram_gb"] = round(int(bits[0]) / (1024 ** 3), 1)
        if len(bits) > 1:
            info["cpu"] = bits[1]
        if len(bits) > 2:
            info["gpu"] = ", ".join(bits[2:])
    except Exception:
        pass
    return info


def bench_one(model, label, prompt, cap):
    """Run one prompt and report what it actually cost."""
    body = {"model": model, "prompt": prompt, "stream": False,
            "options": {"num_predict": cap, "temperature": 0}}
    t0 = time.time()
    try:
        r = post("/api/generate", body)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "HTTP " + str(e.code)}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}
    wall = time.time() - t0

    # Ollama reports nanosecond counters; they are more trustworthy than
    # wall-clock because they exclude our own JSON overhead.
    ev = r.get("eval_count") or 0
    ed = (r.get("eval_duration") or 0) / 1e9
    ld = (r.get("load_duration") or 0) / 1e9
    pd = (r.get("prompt_eval_duration") or 0) / 1e9
    return {
        "ok": True,
        "wall_s": round(wall, 2),
        "load_s": round(ld, 2),
        "first_token_s": round(ld + pd, 2),
        "tokens": ev,
        "tokens_per_s": round(ev / ed, 2) if ed > 0 else None,
        "reply_chars": len(r.get("response") or ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    models = installed()
    if args.only:
        models = [m for m in models if args.only.lower() in m["name"].lower()]

    if args.list or not models:
        print("local models: " + str(len(models)))
        for m in models:
            print("   " + m["name"] + "   " + m["size"])
        return 0

    hw = hardware()
    print("=" * 66)
    print("  " + str(hw["cpu"]))
    print("  GPU: " + str(hw["gpu"]) + "   RAM: " + str(hw["ram_gb"]) + " GB")
    print("  " + str(len(models)) + " models to test")
    print("=" * 66)

    out = {"hardware": hw, "models": {}}
    if os.path.exists(RESULTS):
        try:
            with open(RESULTS, encoding="utf-8") as f:
                out = json.load(f)
            out.setdefault("models", {})
            out["hardware"] = hw
        except Exception:
            pass

    for i, m in enumerate(models, 1):
        name = m["name"]
        print("")
        print("[" + str(i) + "/" + str(len(models)) + "] " + name
              + "  (" + m["size"] + ")")
        entry = {"size": m["size"], "runs": {}}
        for label, prompt, cap in PROMPTS:
            sys.stdout.write("    " + label + " ... ")
            sys.stdout.flush()
            res = bench_one(name, label, prompt, cap)
            entry["runs"][label] = res
            if res.get("ok"):
                print(str(res["tokens_per_s"]) + " tok/s, first token "
                      + str(res["first_token_s"]) + "s, total "
                      + str(res["wall_s"]) + "s")
            else:
                print("FAILED (" + str(res.get("error")) + ")")
        out["models"][name] = entry
        # Written after every model so an interrupted run keeps its results.
        with open(RESULTS, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

    print("")
    print("saved to " + RESULTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
