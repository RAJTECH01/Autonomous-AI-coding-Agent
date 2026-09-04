"""Shared test support: realistic fakes, fixtures factories and assertions.

Design rule for this suite: fake only at process/network boundaries we must not
cross in CI (paid LLM APIs, the Docker daemon when it is absent). Everything
else - the filesystem, the database, the tool layer, the state machine, the HTTP
stack - runs for real.
"""
