import pathlib, sys

bad = [p for p in pathlib.Path('v2/skills').rglob('SKILL.tmpl.md') if not p.read_text().startswith('---')]
sys.exit(1 if bad else 0)
