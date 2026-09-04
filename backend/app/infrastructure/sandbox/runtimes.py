from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LanguageRuntime:
    name: str
    image: str
    default_command: str
    test_command: str
    file_extensions: List[str] = field(default_factory=list)
    description: str = ""


class RuntimeRegistry:
    """
    Registry for sandbox language runtimes enabling multi-language execution
    through separate isolated container base images.
    """

    def __init__(self):
        self._runtimes: Dict[str, LanguageRuntime] = {}
        self._register_default_runtimes()

    def _register_default_runtimes(self):
        # Python Runtime
        self.register_runtime(
            LanguageRuntime(
                name="python",
                image="python:3.11-slim",
                default_command="python",
                test_command="pytest",
                file_extensions=[".py"],
                description="Python 3.11 slim execution runtime",
            )
        )
        # Node.js / JavaScript / TypeScript Runtime
        self.register_runtime(
            LanguageRuntime(
                name="node",
                image="node:20-alpine",
                default_command="node",
                test_command="npm test",
                file_extensions=[".js", ".ts", ".jsx", ".tsx", ".json"],
                description="Node.js 20 Alpine JavaScript & TypeScript runtime",
            )
        )
        # Go Runtime
        self.register_runtime(
            LanguageRuntime(
                name="go",
                image="golang:1.22-alpine",
                default_command="go run",
                test_command="go test ./...",
                file_extensions=[".go"],
                description="Go 1.22 Alpine compiler & test runtime",
            )
        )
        # Rust Runtime
        self.register_runtime(
            LanguageRuntime(
                name="rust",
                image="rust:1.75-slim",
                default_command="cargo run",
                test_command="cargo test",
                file_extensions=[".rs"],
                description="Rust 1.75 slim compilation & test runtime",
            )
        )

    def register_runtime(self, runtime: LanguageRuntime):
        self._runtimes[runtime.name.lower()] = runtime

    def get_runtime(self, name_or_ext: str) -> LanguageRuntime:
        key = name_or_ext.lower().strip()
        # Lookup by exact runtime name
        if key in self._runtimes:
            return self._runtimes[key]

        # Lookup by file extension
        for runtime in self._runtimes.values():
            if key in runtime.file_extensions or f".{key}" in runtime.file_extensions:
                return runtime

        # Default fallback to python
        return self._runtimes["python"]

    def list_runtimes(self) -> Dict[str, LanguageRuntime]:
        return dict(self._runtimes)


# Global default runtime registry instance
runtime_registry = RuntimeRegistry()
