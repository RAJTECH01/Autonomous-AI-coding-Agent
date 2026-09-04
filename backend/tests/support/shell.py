"""A small, real POSIX-shell-semantics command splitter used by the test sandbox.

This is deliberately *not* a mock of shell parsing: it uses ``shlex`` with POSIX
rules, so quoting and word-splitting behave the way ``sh -c`` would. That makes
command-injection assertions meaningful on any host OS, including Windows where
``sh`` is unavailable.
"""

from __future__ import annotations

import shlex
from typing import List

OPERATORS = {"&&", "||", ";", "|"}

# Metacharacters that, if they survive into a command string built from
# untrusted input, mean the caller has a shell-injection defect.
SHELL_METACHARACTERS = (";", "&&", "||", "|", "$(", "`", ">", "<", "\n", "\r")


def split_segments(command: str) -> List[List[str]]:
    """Tokenise a command line and split it into separate command segments.

    ``"find 'a' ; rm -rf b"`` -> ``[["find", "a"], ["rm", "-rf", "b"]]``

    Quoted operators are *not* split, exactly as a real shell would behave, so a
    correctly quoted path containing ``;`` yields a single segment.
    """
    # punctuation_chars makes shlex treat ; & | < > as operator tokens, which is
    # what a real shell does. Plain shlex.split() would fold ";" into the
    # preceding word and hide injection.
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        # Unbalanced quotes: a real shell would error out.
        raise ShellSyntaxError(f"unbalanced quoting in command: {command!r}")

    segments: List[List[str]] = []
    current: List[str] = []
    for token in tokens:
        if token in OPERATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def contains_unquoted_metacharacter(command: str, payload_marker: str) -> bool:
    """True when ``payload_marker`` reached the shell as a separate command.

    Used by injection tests: the marker is a word that only becomes its own
    command segment if the surrounding quoting was broken.
    """
    try:
        segments = split_segments(command)
    except ShellSyntaxError:
        # Unbalanced quotes are themselves proof the payload escaped its quoting.
        return True
    return any(seg and seg[0] == payload_marker for seg in segments)


class ShellSyntaxError(ValueError):
    pass
