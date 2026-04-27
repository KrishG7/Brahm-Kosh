"""Application entry-point fixture."""

import os
import sys
from shared import Shared, shared_helper


def main(argv):
    if not argv:
        return 0
    instance = Shared()
    for arg in argv:
        if arg.startswith("-"):
            continue
        try:
            shared_helper(int(arg))
        except ValueError:
            print(f"bad: {arg}", file=sys.stderr)
    return 0


class App:
    """A small application class."""

    def __init__(self, name):
        self.name = name
        self.shared = Shared()

    def run(self):
        return self.shared.method()

    def greet(self, who):
        if who:
            return f"Hello, {who}"
        return "Hello!"


if __name__ == "__main__":
    sys.exit(main(os.sys.argv[1:]))
