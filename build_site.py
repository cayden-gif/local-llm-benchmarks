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

# Amazon Associates tag. Empty until the account is approved - the links work
# either way, they just earn nothing yet. They were "#ram" and "#minipc"
# placeholders at first, which rendered as dead buttons on a live page.
AMAZON_TAG = os.environ.get("AMAZON_TAG", "")


def amazon(query):
    """A working Amazon search link, with the affiliate tag if one is set."""
    url = "https://www.amazon.com/s?k=" + query.replace(" ", "+")
    return url + ("&tag=" + AMAZON_TAG if AMAZON_TAG else "")


RAM_LINK = amazon("laptop ddr5 sodimm 32gb")
MINIPC_LINK = amazon("mini pc 32gb ram")

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


def warm_first_word(entry, which="medium"):
    """Time to the first word with the model ALREADY loaded.

    The raw first_token figure includes loading the model from disk, and with
    26 models cycling through 16GB of RAM Ollama evicts them constantly - so
    hermes3 looked like it took 6.92s to answer when 6.12s of that was just
    loading. Publishing that as a property of the model would have been wrong.
    Subtracting the load leaves the number people actually care about.
    """
    r = (entry.get("runs") or {}).get(which) or {}
    if not r.get("ok"):
        return None
    ft, ld = r.get("first_token_s"), r.get("load_s")
    if ft is None:
        return None
    return round(max(0.0, ft - (ld or 0.0)), 2)


def cold_load(entry, which="medium"):
    r = (entry.get("runs") or {}).get(which) or {}
    return r.get("load_s") if r.get("ok") else None


def base_name(name):
    """The model without its tag: llama3.2:3b and llama3.2:latest share one."""
    return name.split(":")[0]


def alias_groups(models):
    """Tags that are the same model. Same base name AND same size.

    Two tags of one model produce two near-identical pages, which Google reads
    as thin duplicate content. The canonical is the specific tag rather than
    ":latest", since ":latest" moves over time.
    """
    groups = {}
    for name, entry in models.items():
        key = (base_name(name), entry.get("size"))
        groups.setdefault(key, []).append(name)
    canon = {}
    for key, names in groups.items():
        if len(names) < 2:
            continue
        specific = sorted([n for n in names if not n.endswith(":latest")])             or sorted(names)
        for n in names:
            canon[n] = specific[0]
    return canon


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
        "<th>Speed</th><th>First word</th><th>Cold start</th>"
        "<th>Usable?</th></tr></thead><tbody>",
    ]
    for name, entry, _ in rows:
        tps = speed_of(entry)
        cls, label, _why = verdict(tps)
        warm = warm_first_word(entry)
        cold = cold_load(entry)
        body.append(
            "<tr><td><a href='" + slug(name) + ".html'>" + esc(name)
            + "</a></td><td class=num>" + esc(entry.get("size", "?"))
            + "</td><td class=num>"
            + ((str(tps) + " tok/s") if tps else "&mdash;")
            + "</td><td class=num>"
            + ((str(warm) + "s") if warm is not None else "&mdash;")
            + "</td><td class=num>"
            + ((str(cold) + "s") if cold is not None else "&mdash;")
            + "</td><td><span class='pill " + cls + "'>" + label
            + "</span></td></tr>")
    body += [
        "</tbody></table></div>",
        "<div class=note><b>How to read this.</b> People read at about 5 words "
        "a second, so anything slower feels like waiting. Tokens are roughly "
        "words.<br><b>First word</b> is the wait after hitting enter with the "
        "model already in memory. <b>Cold start</b> is the extra wait when it "
        "has to be loaded from disk, which happens whenever another model has "
        "pushed it out of RAM. They are separated deliberately: combined, they "
        "made hermes3 look like it took 6.9s to answer when 6.1s of that was "
        "purely loading.</div>",
        "<h2>Want to run the bigger ones?</h2>",
        "<p>On hardware like this it is mostly a RAM question: the model has "
        "to fit in memory or the machine swaps and everything stops. "
        "<a href='" + RAM_LINK + "' target=_blank "
        "rel='noopener nofollow sponsored'>RAM upgrades</a> &middot; "
        "<a href='" + MINIPC_LINK + "' target=_blank "
        "rel='noopener nofollow sponsored'>small machines that run these "
        "well</a>"
        "</p>",
    ]
    return page(
        "Local AI benchmarks: " + str(total) + " models on a laptop with no GPU",
        "Measured tokens/sec, load time and usability for " + str(total)
        + " local LLMs on integrated graphics, no CUDA.",
        "\n".join(body), BASE + "/")


def build_model_page(name, entry, hw, canon=None):
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
                           ("First word (incl. any load)", "first_token_s", " s"),
                           ("Cold start - loading from disk", "load_s", " s"),
                           ("Total time", "wall_s", " s"),
                           ("Words generated", "tokens", "")]:
        sv, mv = short.get(key), med.get(key)
        body.append(
            "<tr><td>" + lab + "</td><td class=num>"
            + ((str(sv) + unit) if sv is not None else "&mdash;")
            + "</td><td class=num>"
            + ((str(mv) + unit) if mv is not None else "&mdash;")
            + "</td></tr>")
    warm = warm_first_word(entry)
    if warm is not None:
        body.append("<p>With the model already in memory the first word "
                    "arrives in <b>" + str(warm) + "s</b>. Anything beyond "
                    "that is loading it from disk.</p>")
    if canon and canon != name:
        body.append("<p><b>Same model as <a href='" + slug(canon)
                    + ".html'>" + esc(canon) + "</a></b>, just a different "
                    "tag.</p>")
    body += [
        "</tbody></table></div>",
        "<p>Download size: <b>" + esc(entry.get("size", "?")) + "</b>. The "
        "model has to fit in RAM alongside everything else running, which is "
        "the real limit on a machine like this.</p>",
        "<p><a href='" + RAM_LINK + "' target=_blank "
        "rel='noopener nofollow sponsored'>RAM upgrades</a> &middot; "
        "<a href='./'>Compare all models</a></p>",
    ]
    desc = name + " measured on integrated graphics: " + (
        (str(tps) + " tokens per second.") if tps else "would not run.")
    # A duplicate tag points its canonical at the real page, so Google sees
    # one page instead of two near-identical ones.
    target = canon or name
    return page(title, desc, "\n".join(body),
                BASE + "/" + slug(target) + ".html")


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

    canon = alias_groups(models)
    for name, entry, _ in rows:
        with open(os.path.join(OUT, slug(name) + ".html"), "w",
                  encoding="utf-8") as f:
            f.write(build_model_page(name, entry, hw, canon.get(name)))

    # Only canonical pages belong in a sitemap; alias tags point at them.
    seen, urls = set(), [BASE + "/"]
    for n, _, _ in rows:
        target = canon.get(n, n)
        if target not in seen:
            seen.add(target)
            urls.append(BASE + "/" + slug(target) + ".html")
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
