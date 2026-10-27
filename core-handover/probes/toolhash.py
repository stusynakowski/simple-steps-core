# Core probe (2026-10-26), see docs/core-proposals/011-core-handover.md. Run: .venv/bin/python scripts/core_probes/toolhash.py
import hashlib, inspect, time, sys
from simple_steps_core.grid import tool
@tool
def to_f(t: float) -> float: return t*2
fn = getattr(to_f, "fn", None) or getattr(to_f, "__wrapped__", None) or to_f
print("handle attrs:", [a for a in vars(to_f)] if hasattr(to_f,'__dict__') else type(to_f))
def h(f):
    try: src = inspect.getsource(f)
    except Exception as e: src = None; print("getsource failed:", e)
    code = f.__code__
    by_code = hashlib.sha256(code.co_code + repr(code.co_consts).encode()).hexdigest()[:12]
    return (hashlib.sha256(src.encode()).hexdigest()[:12] if src else None), by_code
t=time.perf_counter(); print("hashes (source, bytecode):", h(fn)); print(f"{(time.perf_counter()-t)*1e3:.2f} ms")
import pandas; print("pandas.read_csv source hash:", h(pandas.read_csv)[0])
