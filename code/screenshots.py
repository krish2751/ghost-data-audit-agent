"""Extract structured records from the evidence PNGs with the model (cached)."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_client

ROOT = llm_client.ROOT
MODEL = "claude-sonnet-5-5"


def png_files():
    with open(ROOT / "dataset" / "evidence_files.csv", newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["file_path"].endswith(".png")]


def extract(row, max_tokens=8000):
    """Return (parsed_json_or_None, call_info) for one manifest row."""
    r = llm_client.call(MODEL, llm_client.load_prompt("screenshot_extract.md"),
                        [ROOT / "dataset" / row["file_path"]], max_tokens=max_tokens, tag=row["file_id"])
    try:
        return llm_client.parse_json(r["text"]), r
    except ValueError:
        return None, r


if __name__ == "__main__":
    for row in png_files():
        data, info = extract(row)
        n = len(data["records"]) if data else None
        print(f"{row['file_id']} {Path(row['file_path']).name:44} cached={info['cached']} "
              f"in={info['usage']['input_tokens']} out={info['usage']['output_tokens']} records={n}")
