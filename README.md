# Local LLM benchmarks on a laptop with no GPU

Measured speed, load time and usability for every Ollama model installed on a
machine with **integrated graphics and no CUDA** — the hardware nobody
benchmarks, because everyone publishing numbers owns a discrete GPU.

**[View the results →](https://cayden-gif.github.io/local-llm-benchmarks/)**

## Why

Search for "can I run llama 3.1 8b" and you get GPU numbers. That tells you
nothing if your laptop has Intel graphics. These numbers were measured on one,
so they answer the question people are actually asking.

Headline: on this hardware anything **3B or under is comfortable**, **7-8B
models run at 6-8 tokens/sec** (usable but you watch it type), and **42GB
models do not fit in 16GB of RAM** at all.

## The rig

| | |
|---|---|
| CPU | Intel Core 7 150U |
| GPU | Intel integrated (no CUDA) |
| RAM | 15.7 GB |
| OS | Windows 11 |

## Reproducing it

```
python bench.py --list     # show what is installed
python bench.py            # benchmark everything (hours)
python build_site.py       # regenerate the pages
```

`bench.py` measures two prompts per model — a short one and a longer one —
because time-to-first-token and tokens-per-second are different problems.
Time-to-first-token is what makes a model *feel* slow; tokens/sec is what makes
a long answer painful. Results save after every model, so an interrupted run
loses nothing.

## Method notes

- Timings come from Ollama's own nanosecond counters (`eval_duration`,
  `load_duration`), not wall-clock, so JSON overhead is excluded.
- `temperature: 0` for repeatability.
- A model that does not answer within 7 minutes is recorded as "won't run",
  which is a useful result rather than a failure.
- Cloud-hosted Ollama entries are skipped — benchmarking those would measure
  someone else's datacentre.

## Licence

MIT. The data is free to use; a link back is appreciated.
