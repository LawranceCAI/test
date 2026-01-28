#!/usr/bin/env python3
"""
Convert a Word .docx note into mixed review cards (QA + Cloze + Recall),
then write to web/data/cards.json for the Commute Review PWA.

Usage:
  python tools/build_cards.py "source/Key Review.docx" "web/data/cards.json"
"""
import re, json, datetime, sys
from pathlib import Path
from docx import Document

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def is_heading(style: str, text: str) -> bool:
    # ONLY top-level headings become topics
    return (style or "").strip() == "Heading 1"

def split_bullets(text: str):
    t = norm(text)
    if ";" in t and len(t) > 40:
        parts = [norm(p) for p in t.split(";") if norm(p)]
        if len(parts) >= 3:
            return parts
    return [t]

EQ_PAT = re.compile(r"^(.{2,120}?)\s*=\s*(.{8,})$")
COLON_PAT = re.compile(r"^(.{2,120}?)\s*:\s*(.{8,})$")

def build_cards(docx_path: Path):
    doc = Document(str(docx_path))
    paras = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if not text:
            continue
        style = (p.style.name if p.style else "")
        paras.append((style, text))

    sections = []
    current = {"title": "General", "items": []}
    for style, text in paras:
        if is_heading(style, text.strip()):
            if current["items"]:
                sections.append(current)
            current = {"title": text.strip(), "items": []}
        else:
            current["items"].append(text.strip())
    if current["items"]:
        sections.append(current)

    cards = []
    cid = 1
    def add(card):
        nonlocal cid
        card["id"] = f"c{cid:05d}"
        cid += 1
        cards.append(card)

    for sec in sections:
        topic = sec["title"]
        for raw in sec["items"]:
            for line in split_bullets(raw):
                t = norm(line)

                if not t:
                    continue

                # Cloze markers: {{answer}}
                if "{{" in t and "}}" in t:
                    prompt = re.sub(r"\{\{(.*?)\}\}", "_____", t)
                    answers = re.findall(r"\{\{(.*?)\}\}", t)
                    add({"type":"cloze","topic":topic,"prompt":prompt,"answer":"; ".join(answers),"source":"docx"})
                    continue

                m = EQ_PAT.match(t)
                if m:
                    term, definition = norm(m.group(1)), norm(m.group(2))
                    add({"type":"qa","topic":topic,"prompt":f"Define: {term}","answer":definition,"source":"docx"})
                    add({"type":"cloze","topic":topic,"prompt":f"_____: {definition}","answer":term,"source":"docx"})
                    continue

                m = COLON_PAT.match(t)
                if m and "e.g." not in m.group(1).lower():
                    term, definition = norm(m.group(1)), norm(m.group(2))
                    if len(term.split()) <= 12 and len(definition) >= 10:
                        add({"type":"qa","topic":topic,"prompt":f"What is {term}?","answer":definition,"source":"docx"})
                        add({"type":"cloze","topic":topic,"prompt":f"{term}: _____","answer":definition,"source":"docx"})
                        continue

                if "→" in t:
                    parts = [norm(p) for p in t.split("→") if norm(p)]
                    if len(parts) >= 2:
                        add({"type":"cloze","topic":topic,"prompt":parts[0] + " → _____","answer":" → ".join(parts[1:]),"source":"docx"})
                        continue

                # Recall statements
                if 25 <= len(t) <= 220 and any(k in t.lower() for k in [" is ", " are ", " refers to", " suggests", " explains", " occurs", " means"]):
                    add({"type":"recall","topic":topic,"prompt":"Recall this key point:","answer":t,"source":"docx"})

    # de-dup
    seen=set()
    dedup=[]
    for c in cards:
        key=(c["type"], c["prompt"], c["answer"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)

    meta = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_file": docx_path.name,
        "card_count": len(dedup),
        "topics": sorted({c["topic"] for c in dedup}),
    }
    return {"meta": meta, "cards": dedup}

def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = build_cards(in_path)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {data['meta']['card_count']} cards -> {out_path}")

if __name__ == "__main__":
    main()
