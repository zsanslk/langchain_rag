# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import docx

files = [
    'uploads/8_1ebd9c6d.docx',
    'uploads/8_324c9438.docx',
    'uploads/8_99986251.docx',
]

for f in files:
    path = os.path.join(r'd:\毕业设计\langchian310', f)
    print(f"\n=== FILE: {f} ===")
    try:
        d = docx.Document(path)
        text = '\n'.join(p.text for p in d.paragraphs if p.text.strip())
        # Just print first 2000 chars to see the topics
        print(text[:2000])
        print(f"\n... [Total {len(text)} chars]")
    except Exception as e:
        print(f"Error: {e}")

# Also check the a7a4eb65.txt and cb7f48e3.txt (may be duplicates)
print("\n=== Checking txt duplicates ===")
for f in ['uploads/8_a7a4eb65.txt', 'uploads/8_cb7f48e3.txt']:
    path = os.path.join(r'd:\毕业设计\langchian310', f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    print(f"{f}: first 100 chars = {content[:100]}")
