"""Build the evaluation inputs from pinned public datasets.

Each output line: {"id", "inputs": {input_name: text}, "label": secret attribute,
"gold": task ground truth (optional), ...}. Sampling is seeded and balanced
over the secret label. Revisions are pinned to Hugging Face commit hashes.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re

import pandas as pd
from huggingface_hub import hf_hub_download

REV = {
    "fancyzhx/dbpedia_14": "9abd46cf7fc8b4c64290f26993c540b92aa145ac",
    "bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset": "12dd624ddcd3057382b2faad661bcda1fa869491",
    "Tobi-Bueck/customer-support-tickets": "ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb",
    "rajpurkar/squad": "7b6d24c440a36b6815f21b70d25016731768db1f",
    "rajpurkar/squad_v2": "3ffb306f725f7d2ce8394bc1873b24868140c412",
    "openai/gsm8k": "740312add88f781978c0658806c59bc2815b9866",
}
DBPEDIA = ["Company", "EducationalInstitution", "Artist", "Athlete", "OfficeHolder", "MeanOfTransportation",
           "Building", "NaturalPlace", "Village", "Animal", "Plant", "Album", "Film", "WrittenWork"]


def get(repo, path):
    p = hf_hub_download(repo, path, repo_type="dataset", revision=REV[repo])
    return pd.read_parquet(p) if path.endswith(".parquet") else pd.read_csv(p)


def balanced(rows, key, per, rng):
    by = {}
    for r in rows:
        by.setdefault(r[key], []).append(r)
    out = []
    for k in sorted(by):
        rng.shuffle(by[k])
        out += by[k][:per]
    rng.shuffle(out)
    return out


def write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(path, len(rows))


def dbpedia_topics(rng, classes, per):
    df = get("fancyzhx/dbpedia_14", "dbpedia_14/test-00000-of-00001.parquet")
    rows = [{"title": t, "label": DBPEDIA[l]} for t, l in zip(df.title, df.label) if DBPEDIA[l] in classes]
    return balanced(rows, "label", per, rng)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiments/data")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)

    # Routing: user requests for a story, joke or poem about a DBpedia topic.
    forms = {
        "story": ["Write me a story about {t}", "Tell a short tale involving {t}", "Can you narrate a story about {t}?",
                  "I'd like a bedtime story featuring {t}"],
        "joke": ["Write me a joke about {t}", "Tell me something funny about {t}", "Make me laugh with a joke on {t}",
                 "Give me a pun about {t}"],
        "poem": ["Write me a poem about {t}", "Compose some verses about {t}", "Can you write a haiku about {t}?",
                 "I'd like a sonnet on {t}"],
    }
    # Person classes are excluded: the small instruct models refuse jokes/stories about real people.
    nonperson = [c for c in DBPEDIA if c not in ("Artist", "Athlete", "OfficeHolder")]
    topics = dbpedia_topics(rng, nonperson, 30)
    rows = []
    for k, tp in enumerate(topics[:150]):
        form = ["story", "joke", "poem"][k % 3]
        text = rng.choice(forms[form]).format(t=tp["title"])
        rows.append({"id": f"route-{k}", "inputs": {"user_input": text}, "label": form, "gold": form})
    write(f"{args.out}/routing.jsonl", rows)

    # DBpedia topic workflows (chaining, evaluator-optimizer, orchestrator-worker).
    five = ["Company", "MeanOfTransportation", "Village", "Film", "Animal"]
    for name, per in [("chaining", 30), ("evaluator", 20), ("orchestrator", 20)]:
        tps = dbpedia_topics(random.Random(args.seed + len(name)), five, per)
        pre = "Create a report on " if name == "orchestrator" else ""
        rows = [{"id": f"{name}-{k}", "inputs": {"topic": pre + t["title"]}, "label": t["label"]}
                for k, t in enumerate(tps)]
        write(f"{args.out}/{name}.jsonl", rows)

    # Prompt Flow switch: retail intents mapped to the flow's classes.
    df = get("bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset",
             "bitext-retail-ecommerce-llm-chatbot-training-dataset.csv")
    m = {"track_order": "order_search", "order_history": "order_search", "change_order": "order_search",
         "cancel_order": "order_search", "product_information": "product_info", "availability": "product_info",
         "availability_online": "product_info", "availability_in_store": "product_info"}
    rows = []
    for ins, intent in zip(df.instruction, df.intent):
        lab = m.get(intent, "unknown")
        rows.append({"q": ins, "label": lab})
    rows = balanced(rows, "label", 70, rng)
    write(f"{args.out}/switch.jsonl", [{"id": f"switch-{k}", "inputs": {"query": r["q"]}, "label": r["label"],
                                         "gold": r["label"]} for k, r in enumerate(rows)])

    # Email support: synthetic support tickets (English), label = queue family.
    df = get("Tobi-Bueck/customer-support-tickets", "aa_dataset-tickets-multi-lang-5-2-50-version.csv")
    df = df[df.language == "en"].dropna(subset=["body"])
    fam = lambda q: ("billing" if "Billing" in q else "technical" if "Technical" in q or "IT Support" in q
                     else "product" if "Product" in q else "other")
    rows = [{"email": (str(s) + "\n\n" + str(b)).strip() if isinstance(s, str) else str(b), "label": fam(str(q)),
             "priority": str(p)} for s, b, q, p in zip(df.subject, df.body, df.queue, df.priority)]
    rows = [r for r in rows if len(r["email"]) < 1200]
    rows = balanced(rows, "label", 38, rng)
    write(f"{args.out}/email.jsonl", [{"id": f"email-{k}", "inputs": {"email_content": r["email"]},
                                        "label": r["label"], "priority": r["priority"]} for k, r in enumerate(rows)])

    # RAG corpora from SQuAD v1.1 (CRAG) and v2 (adaptive RAG): half the titles indexed.
    for name, repo, path, per in [("crag", "rajpurkar/squad", "plain_text/validation-00000-of-00001.parquet", 75),
                                  ("adaptive", "rajpurkar/squad_v2", "squad_v2/validation-00000-of-00001.parquet", 30)]:
        df = get(repo, path)
        titles = sorted(set(df.title))
        r2 = random.Random(args.seed + 11)
        r2.shuffle(titles)
        indexed = set(titles[: len(titles) // 2])
        ctx = df.drop_duplicates("context")
        corpus = [{"text": c, "title": t} for c, t in zip(ctx.context, ctx.title) if t in indexed]
        web = [{"text": c, "title": t} for c, t in zip(ctx.context, ctx.title) if t not in indexed]
        write(f"{args.out}/{name}_corpus.jsonl", corpus)
        write(f"{args.out}/{name}_web.jsonl", web)
        qs = []
        for q, t, a, c in zip(df.question, df.title, df.answers, df.context):
            ans = list(a["text"])
            lab = "in_corpus" if t in indexed else "out_of_corpus"
            if name == "adaptive":
                lab += "/answerable" if ans else "/unanswerable"
            qs.append({"q": q, "label": lab, "answers": ans, "context": c, "title": t})
        qs = balanced(qs, "label", per, rng)
        write(f"{args.out}/{name}.jsonl", [{"id": f"{name}-{k}", "inputs": {"question": r["q"]}, "label": r["label"],
                                             "answers": r["answers"], "title": r["title"]} for k, r in enumerate(qs)])
        with open(f"{args.out}/{name}_indexed_titles.json", "w") as f:
            json.dump(sorted(indexed), f)

    # Calculator agent: GSM8K, label = number of reference calculator steps.
    df = get("openai/gsm8k", "main/test-00000-of-00001.parquet")
    rows = []
    for q, a in zip(df.question, df.answer):
        steps = len(re.findall(r"<<[^>]*>>", a))
        b = "1-2" if steps <= 2 else "3" if steps == 3 else "4" if steps == 4 else "5+"
        rows.append({"q": q, "label": b, "final": a.split("####")[-1].strip().replace(",", "")})
    rows = balanced(rows, "label", 25, rng)
    write(f"{args.out}/calculator.jsonl", [{"id": f"calc-{k}", "inputs": {"question": r["q"]}, "label": r["label"],
                                            "gold": r["final"]} for k, r in enumerate(rows)])


if __name__ == "__main__":
    main()
