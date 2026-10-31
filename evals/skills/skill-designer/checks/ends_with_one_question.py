#!/usr/bin/env python3
"""Expectation check: the final message asks exactly one question, and it is the message's last sentence.

The final message is `final-message.md` next to the run's output folder. Code spans and blocks are removed
first, so a `?` inside quoted code is not counted as a question.

Argument: the run's output folder. Exit 0 when the expectation holds.
"""

import re
import sys
from pathlib import Path


def main(outputs):
    path = Path(outputs).parent / "final-message.md"
    if not path.is_file():
        print("final-message.md not found")
        return 1
    text = re.sub(r"```.*?```", " ", path.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text).strip()
    count = text.count("?")
    last = text.rstrip(" *_)\"'”").endswith("?")
    print(f"question marks: {count}; ends with a question: {last}")
    return 0 if count == 1 and last else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
