"""Turn measured benchmark results into a static site.

No template engine and no framework: the output is plain files that any free
host will serve, and the DATA is the product. Nothing in here should be more
complicated than the numbers it presents.

    python build_site.py

Reads results.json (written by bench.py) and writes ./site/
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.json")
OUT = os.path.join(HERE, "site")
USER = os.environ.get("GH_USER", "cayden-gif")
REPO = os.environ.get("GH_REPO", "local-llm-benchmarks")
BASE = "https://" + USER + ".github.io/" + REPO

# Placeholders for affiliate links, so adding them later is a find-and-replace
# rather than a rebuild.
RAM_LINK = "#ram"
MINIPC_LINK = "#minipc"

CSS = """
:root{--bg:#0d1117;--card:#161b22;--edge:#30363d;--ink:#e6edf3;
  --dim:#8b949e;--good:#3fb950;--warn:#d29922;--bad:#f85149;--link:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,Segoe UI,system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:32px 20px 64px}
a{color:var(--link)}
h1{font-size:1.9rem;line-height:1.25;margin:0 0 8px}
h2{font-size:1.25rem;margin:40px 0 12px}
.sub{color:var(--dim);margin:0 0 28px}
.rig{background:var(--card);border:1px solid var(--edge);border-radius:10px;
  padding:14px 16px;margin:0 0 28px;font-size:.9rem;color:var(--dim)}
.rig b{color:var(--ink);font-weight:600}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;min-width:560px;font-size:.94rem}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--edge)}
th{color:var(--dim);font-weight:600;font-size:.82rem;text-transform:uppercase;
  letter-spacing:.04em;white-space:nowrap}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
tr:hover td{background:#1c2128}
.ok{color:var(--good)}.mid{color:var(--warn)}.no{color:var(--bad)}
.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.78rem;
  border:1px solid currentColor}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--edge);
  color:var(--dim);font-size:.85rem}
.note{background:var(--card);border-left:3px solid var(--link);
  border-radius:0 8px 8px 0;padding:12px 16px;margin:24px 0;font-size:.93rem}
"""


def slug(name):
    """A filename-safe version of a name like hf.co/OBLITERATUS/x:Q4_K_M."""
    keep = []
    for ch in name.lower():
        keep.append(ch if ch.isalnum() else "-")
    s = "".join(keep)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def verdict(tps):
    """Plain-language answer to "is this usable", from the measured speed.

    People read at roughly 5 words a second, so anything slower feels like
    waiting. The thresholds are deliberately blunt: a number with no
    interpretation does not answer the question anyone is actually asking.
    """
    if tps is None:
        return "no", "won't run", "Failed or timed out on this hardware."
    if tps >= 25:
        return "ok", "instant", "Faster than you can read. Comfortable for chat."
    if tps >= 12:
        return "ok", "fine", "Comfortable for conversation."
    if tps >= 5:
        return "mid", "slow", "Usable, but you will watch it type."
    if tps >= 1.5:
        return "mid", "painful", "Long waits. Fine for one-off jobs, not chat."
    return "no", "unusable", "Too slow to interact with."


def esc(s):
    return html.escape(str(s), quote=True)


def page(title, desc, body, canonical):
    head = [
        "<!doctype html>", "<html lang=en>", "<head>", "<meta charset=utf-8>",
        "<meta name=viewport content='width=device-width,initial-scale=1'>",
        "<title>" + esc(title) + "</title>",
        "<meta name=description content='" + esc(desc) + "'>",
        "<link rel=canonical href='" + canonical + "'>",
        "<meta property='og:title' content='" + esc(title) + "'>",
        "<style>" + CSS + "</style>", "</head>", "<body><div class=wrap>",
    ]
    foot = [
        "<footer>Every number here was measured on the machine described "
        "above, not estimated or copied. <a href='" + BASE + "/'>All results"
        "</a></footer>", "</div></body></html>", "",
    ]
    return "\n".join(head + [body] + foot)


def speed_of(entry, which="medium"):
    r = (entry.get("runs") or {}).get(which) or {}
    return r.get("tokens_per_s") if r.get("ok") else None


def rig_block(hw):
    return ("<div class=rig>Measured on <b>" + esc(hw.get("cpu", "?"))
            + "</b> &middot; GPU <b>" + esc(hw.get("gpu", "?"))
            + "</b> &middot; <b>" + esc(hw.get("ram_gb", "?"))
            + " GB</b> RAM &middot; " + esc(hw.get("os", "")) + "</div>")


def build_index(rows, hw, total):
    body = [
        "<h1>Local AI models on a laptop with no graphics card</h1>",
        "<p class=sub>Real measurements from " + str(total) + " models running "
        "on integrated graphics: speed, load time, and whether each one is "
        "actually usable.</p>",
        rig_block(hw),
        "<div class=scroll><table><thead><tr><th>Model</th><th>Size</th>"
        "<th>Speed</th><th>First word</th><th>Usable?</th></tr></thead><tbody>",
    ]
    for name, entry, _ in rows:
        tps = speed_of(entry)
        cls, label, _why = verdict(tps)
        med = (entry.get("runs") or {}).get("medium") or {}
        ftt = med.get("first_token_s")
        body.append(
            "<tr><td><a href='" + slug(name) + ".html'>" + esc(name)
            + "</a></td><td class=num>" + esc(entry.get("size", "?"))
            + "</td><td class=num>"
            + ((str(tps) + " tok/s") if tps else "&mdash;")
            + "</td><td class=num>"
            + ((str(ftt) + "s") if ftt is not None else "&mdash;")
            + "</td><td><span class='pill " + cls + "'>" + label
            + "</span></td></tr>")
    body += [
        "</tbody></table></div>",
        "<div class=note><b>How to read this.</b> People read at about 5 words "
        "a second, so anything slower feels like waiting. Tokens are roughly "
        "words. First-word time is how long you stare at nothing after hitting "
        "enter, and it is usually what makes a model feel slow rather than the "
        "typing speed.</div>",
        "<h2>Want to run the bigger ones?</h2>",
        "<p>On hardware like this it is mostly a RAM question: the model has "
        "to fit in memory or the machine swaps and everything stops. "
        "<a href='" + RAM_LINK + "'>RAM upgrades</a> &middot; "
        "<a href='" + MINIPC_LINK + "'>small machines that run these well</a>"
        "</p>",
    ]
    return page(
        "Local AI benchmarks: " + str(total) + " models on a laptop with no GPU",
        "Measured tokens/sec, load time and usability for " + str(total)
        + " local LLMs on integrated graphics, no CUDA.",
        "\n".join(body), BASE + "/")


def build_model_page(name, entry, hw):
    tps = speed_of(entry)
    cls, label, why = verdict(tps)
    short = (entry.get("runs") or {}).get("short") or {}
    med = (entry.get("runs") or {}).get("medium") or {}
    title = "Can you run " + name + " without a GPU?"
    body = [
        "<h1>" + esc(title) + "</h1>",
        "<p class=sub><span class='pill " + cls + "'>" + label + "</span> "
        "&nbsp; " + esc(why) + "</p>",
        rig_block(hw),
        "<div class=scroll><table><thead><tr><th>Measurement</th>"
        "<th>Short reply</th><th>Longer reply</th></tr></thead><tbody>",
    ]
    for lab, key, unit in [("Speed", "tokens_per_s", " tok/s"),
                           ("Time to first word", "first_token_s", " s"),
                           ("Model load", "load_s", " s"),
                           ("Total time", "wall_s", " s"),
                           ("Words generated", "tokens", "")]:
        sv, mv = short.get(key), med.get(key)
        body.append(
            "<tr><td>" + lab + "</td><td class=num>"
            + ((str(sv) + unit) if sv is not None else "&mdash;")
            + "</td><td class=num>"
            + ((str(mv) + unit) if mv is not None else "&mdash;")
            + "</td></tr>")
    body += [
        "</tbody></table></div>",
        "<p>Download size: <b>" + esc(entry.get("size", "?")) + "</b>. The "
        "model has to fit in RAM alongside everything else running, which is "
        "the real limit on a machine like this.</p>",
        "<p><a href='" + RAM_LINK + "'>RAM upgrades</a> &middot; "
        "<a href='./'>Compare all models</a></p>",
    ]
    desc = name + " measured on integrated graphics: " + (
        (str(tps) + " tokens per second.") if tps else "would not run.")
    return page(title, desc, "\n".join(body),
                BASE + "/" + slug(name) + ".html")


def main():
    try:
        with open(RESULTS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("no results yet (" + type(e).__name__ + "). Run bench.py first.")
        return 1

    hw = data.get("hardware", {})
    models = data.get("models", {})
    if not models:
        print("results.json has no models yet. Run bench.py first.")
        return 1

    os.makedirs(OUT, exist_ok=True)

    # Fastest first; anything that would not run sinks to the bottom.
    rows = []
    for name, entry in models.items():
        tps = speed_of(entry)
        rows.append((name, entry, tps if tps is not None else -1))
    rows.sort(key=lambda r: r[2], reverse=True)

    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(rows, hw, len(models)))

    for name, entry, _ in rows:
        with open(os.path.join(OUT, slug(name) + ".html"), "w",
                  encoding="utf-8") as f:
            f.write(build_model_page(name, entry, hw))

    urls = [BASE + "/"] + [BASE + "/" + slug(n) + ".html" for n, _, _ in rows]
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n"
                "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n"
                + "".join("<url><loc>" + u + "</loc></url>\n" for u in urls)
                + "</urlset>\n")
    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: " + BASE + "/sitemap.xml\n")

    print("built " + str(len(rows) + 1) + " pages into " + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
