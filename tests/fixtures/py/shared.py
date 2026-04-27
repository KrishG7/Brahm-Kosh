"""Sibling module used as a resolution target in tests."""


def shared_helper(x):
    return x + 1


class Shared:
    def method(self):
        return "shared"
