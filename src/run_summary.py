#!/usr/bin/env python3
"""
Minimal runner for ChatGPT-based news summarization experiments.

Usage:
  python src/run_summary.py --csv data/sample.csv --prompt prompts/summarize.txt --dry-run

Behavior:
  - Reads column-based CSV with headers: id,article,summary
  - For rows where `summary` is empty, calls the OpenAI ChatCompletion API and writes the result into `summary`
  - Writes back to the same CSV (atomic write to tmp file)
"""


import argparse
import csv
import os
import sys
import tempfile
import json
import time

# dotenv is optional in execution env (we allow --dry-run without it)
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return None

from typing import List

# make sure src/ is on path so `utils` can be imported when running this file from repo root
sys.path.insert(0, os.path.dirname(__file__))
from utils import load_prompt, render_prompt, retry_backoff

try:
    import openai
except Exception:
    openai = None


def call_openai_chat(prompt: str, model: str = "gpt-3.5-turbo") -> str:
    if openai is None:
        raise RuntimeError("openai package not installed")

    # Try old (v0.x) interface first: openai.ChatCompletion.create
    try:
        if hasattr(openai, "ChatCompletion"):
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.2,
            )
            # dict-like response
            choices = resp.get("choices") or []
            if choices:
                first = choices[0]
                # dict-style
                if isinstance(first, dict) and "message" in first and "content" in first["message"]:
                    return first["message"]["content"].strip()
                # object-style
                if hasattr(first, "message") and hasattr(first.message, "content"):
                    return first.message.content.strip()

    except Exception:
        # fallback to trying new API below
        pass

    # Try new (v1.x) interface: openai.OpenAI().chat.completions.create
    try:
        client = None
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI()
        else:
            # some installs expose OpenAI class on package
            try:
                from openai import OpenAI as _OpenAI
                client = _OpenAI()
            except Exception:
                client = None

        if client is not None and hasattr(client, "chat"):
            # chat.completions.create
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.2,
            )
            # try object-like access
            try:
                choices = getattr(resp, "choices", None)
                if choices:
                    first = choices[0]
                    if hasattr(first, "message") and hasattr(first.message, "content"):
                        return first.message.content.strip()
            except Exception:
                pass
            # try dict-like
            try:
                d = dict(resp)
                choices = d.get("choices") or []
                if choices:
                    first = choices[0]
                    if isinstance(first, dict) and "message" in first and "content" in first["message"]:
                        return first["message"]["content"].strip()
            except Exception:
                pass

        # Some newer interfaces may use responses.create (fallback)
        if client is not None and hasattr(client, "responses"):
            resp = client.responses.create(
                model=model,
                input=prompt,
                max_tokens=256,
            )
            # Try to extract text from common response shapes
            # 1) resp.output_text (string)
            if hasattr(resp, "output_text"):
                return str(resp.output_text).strip()
            # 2) resp.output -> list of dicts
            try:
                d = dict(resp)
                # Look for 'output' or 'choices'
                if "output" in d and isinstance(d["output"], list) and d["output"]:
                    first = d["output"][0]
                    # nested content
                    if isinstance(first, dict):
                        # try text fields
                        for key in ("content", "text", "body"):
                            if key in first:
                                return str(first[key]).strip()
            except Exception:
                pass

    except Exception:
        # final fallback
        pass

    raise RuntimeError("Unable to call OpenAI chat completion with detected openai package interface")


def process_csv(csv_path: str, prompt_path: str, model: str, batch_size: int = 5, dry_run: bool = False):
    prompt_template = load_prompt(prompt_path)
    rows = []
    updated = False

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        if headers is None or "article" not in headers or "summary" not in headers:
            print("CSV must include headers and contain 'article' and 'summary' columns.")
            sys.exit(1)
        for r in reader:
            rows.append(r)

    # iterate and process missing summaries
    for i, row in enumerate(rows):
        if row.get("summary") and row.get("summary").strip():
            continue
        article = row.get("article", "")
        prompt = render_prompt(prompt_template, article)
        print(f"Processing id={row.get('id')} (index={i})")
        if dry_run:
            # print a short preview instead of calling API
            print("--- prompt preview ---")
            print(prompt[:1000])
            print("--- end preview ---")
            row["summary"] = "[dry-run] summary would be written here"
            updated = True
            continue

        def _call():
            return call_openai_chat(prompt, model=model)

        try:
            summary = retry_backoff(_call, max_retries=4, base=1, exceptions=(Exception,))
        except Exception as e:
            print(f"Error calling OpenAI for id={row.get('id')}: {e}")
            with open("errors.log", "a", encoding="utf-8") as ef:
                ef.write(json.dumps({"id": row.get("id"), "error": str(e)}) + "\n")
            continue

        row["summary"] = summary
        updated = True
        # simple rate-limiting control
        time.sleep(0.3)

    if updated:
        # write atomically
        tmp_dir = os.path.dirname(os.path.abspath(csv_path)) or "."
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="csvtmp", suffix=".csv", dir=tmp_dir)
        with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as wf:
            writer = csv.DictWriter(wf, fieldnames=headers)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        os.replace(tmp_path, csv_path)
        print(f"Wrote updates to {csv_path}")
    else:
        print("No updates needed.")


def main(argv: List[str]):
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/sample.csv", help="Path to CSV file (headers: id,article,summary). Default: data/sample.csv")
    p.add_argument("--prompt", default="prompts/summarize.txt", help="Path to prompt template. Default: prompts/summarize.txt")
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"))
    p.add_argument("--batch-size", type=int, default=5)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not args.dry_run and not api_key:
        print("OPENAI_API_KEY not set. Copy .env.example to .env and set your key, or run with --dry-run.")
        sys.exit(1)
    if openai is not None and api_key:
        openai.api_key = api_key

    process_csv(args.csv, args.prompt, args.model, batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main(sys.argv[1:])
