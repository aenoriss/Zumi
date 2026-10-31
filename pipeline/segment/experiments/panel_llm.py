"""Hard boxes of the panel bake-off through vision LLMs (OpenRouter, spend-capped): each returns the drawn panels as
boxes in 0-1000 coordinates; written into speakers/bakeoff.json as methods llm_<model> for the reviewer. Scored
against llm_opus5.5 by panel_score.py (2026-10-30: Gemini 3.1 Pro, Sonnet 5.5 and GPT-5.6 Terra matched it on all
6 hard boxes; Sonnet 5.5, which never varied over repeated calls (panel_repeat.py), became the pipeline's frame
finder, frames.py, whose prompt and call this uses).

    uv run python experiments/panel_llm.py <out root> <pid> [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import frames as FR  # noqa: E402
import openrouter as OR  # noqa: E402

# name -> (OpenRouter id, reasoning effort, or None for models without a reasoning switch)
MODELS = {
    "llm_opus5.5": ("anthropic/claude-opus-5.5", "low"),
    "llm_maverick": ("meta-llama/llama-4-maverick", None),
    "llm_gemini3.8": ("google/gemini-3.8-flash", "low"),
    "llm_sonnet5.5": ("anthropic/claude-sonnet-5.5", "low"),
    "llm_haiku5.5": ("anthropic/claude-haiku-5.5", "low"),
    "llm_gpt5.6terra": ("openai/gpt-5.6-terra", "low"),
    "llm_gpt5.6luna": ("openai/gpt-5.6-luna", "low"),
    "llm_gemini3.1pro": ("google/gemini-3.1-pro-preview", "low"),
    "llm_qwen3vl235": ("qwen/qwen3-vl-235b-a22b-instruct", None),
    "llm_qwen3.8flash": ("qwen/qwen3.8-flash", None),
    "llm_scout": ("meta-llama/llama-4-scout", None),
    "llm_grok4.7": ("x-ai/grok-4.7", "low"),
    "llm_glm5v": ("z-ai/glm-5v-turbo", None),
    "llm_mistralmed3.5": ("mistralai/mistral-medium-3-5", None),
}


def ask(model: str, reasoning: str | None, img: Image.Image, tag: str) -> list[list[float]]:
    """The pipeline's own prompt and call (frames.ask), with another model."""
    return FR.ask(img, model, reasoning, tag)


def main() -> None:
    root = Path(sys.argv[1]); pids = sys.argv[2:]
    path = root / "speakers" / "bakeoff.json"
    bk = json.loads(path.read_text())
    for name, (model, reasoning) in MODELS.items():
        per = bk["methods"].setdefault(name, {})
        for pid in pids:
            if pid in per:  # answered before: kept, not paid for twice
                continue
            img = Image.open(root / "speakers" / "boxes" / f"{pid}.jpg").convert("RGB")
            w, h = img.size
            try:
                boxes = ask(model, reasoning, img, f"panels:{pid}")
            except OR.BudgetExceeded as e:
                print("STOP:", e); break
            except Exception as e:  # a malformed answer: no panels from this model for this box
                print(f"{name} {pid}: {type(e).__name__} {e}"); boxes = []
            rings = []
            for b in boxes:
                if len(b) == 4:
                    x0, y0, x1, y1 = (b[0] * w / 1000, b[1] * h / 1000, b[2] * w / 1000, b[3] * h / 1000)
                    rings.append({"rings": [[[int(x0), int(y0)], [int(x1), int(y0)], [int(x1), int(y1)], [int(x0), int(y1)]]], "score": None})
            per[pid] = rings
            print(f"{name} {pid}: {len(rings)} panels", flush=True)
            path.write_text(json.dumps(bk))
    print(f"spent today: {OR.spent_today():.3f} USD")


if __name__ == "__main__":
    main()
