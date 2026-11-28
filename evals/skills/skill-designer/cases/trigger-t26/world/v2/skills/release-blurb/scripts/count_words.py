"""Count the words of a release blurb, and exit 1 when it is longer than 80 words."""

import re
import sys

LIMIT = 80


def count(text):
    return len([word for word in re.split(r"[\s\-]+", text) if word])


def main(path):
    with open(path, encoding="utf-8") as handle:
        words = count(handle.read())
    print(f"{words} words (limit {LIMIT})")
    return 0 if words <= LIMIT else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
