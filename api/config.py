"""
Configuration for vbase-rce
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RuntimeConfig:
    """Configuration for a language runtime"""

    language: str
    version: str
    aliases: List[str]
    image: str
    extension: str
    compiled: bool = False
    compile_cmd: Optional[str] = None
    run_cmd: str = ""
    runtime: Optional[str] = None


@dataclass
class SecurityConfig:
    """Security constraints for container execution"""

    # Memory limits
    default_memory_limit: str = "128m"  # 128 MB
    max_memory_limit: str = "256m"  # 256 MB

    # CPU limits
    cpu_period: int = 100000  # microseconds
    cpu_quota: int = 50000  # 50% of one CPU
    nano_cpus: int = 500000000  # 0.5 CPUs

    # Timeout limits (in seconds)
    default_timeout: int = 10
    max_timeout: int = 30

    # Process limits
    pids_limit: int = 64  # Max number of processes

    # Filesystem
    read_only_rootfs: bool = True
    tmpfs_size: str = "64m"  # 64 MB tmpfs for /tmp

    # Network
    network_disabled: bool = True

    # Capabilities - drop all, add none
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])

    # Security options
    security_opt: List[str] = field(default_factory=lambda: ["no-new-privileges:true"])

    # User
    user: str = "runner"


# Available runtimes configuration
RUNTIMES: List[RuntimeConfig] = [
    RuntimeConfig(
        language="python",
        version="3.12.0",
        aliases=["python3", "py"],
        image="vbase-python-runner",
        extension=".py",
        compiled=False,
        run_cmd="python3 {file} {args}",
    ),
    RuntimeConfig(
        language="javascript",
        version="20.0.0",
        aliases=["js", "node", "node-js"],
        image="vbase-node-runner",
        extension=".js",
        compiled=False,
        runtime="node",
        run_cmd="node {file} {args}",
    ),
    RuntimeConfig(
        language="c",
        version="13.2.0",
        aliases=["gcc"],
        image="vbase-c-runner",
        extension=".c",
        compiled=True,
        compile_cmd="gcc -o /tmp/program {file} -lm",
        run_cmd="/tmp/program {args}",
    ),
    RuntimeConfig(
        language="c++",
        version="13.2.0",
        aliases=["cpp", "g++", "cplusplus"],
        image="vbase-cpp-runner",
        extension=".cpp",
        compiled=True,
        compile_cmd="g++ -o /tmp/program {file} -lm",
        run_cmd="/tmp/program {args}",
    ),
    RuntimeConfig(
        language="go",
        version="1.22.0",
        aliases=["golang"],
        image="vbase-go-runner",
        extension=".go",
        compiled=True,
        compile_cmd="go build -o /tmp/program {file}",
        run_cmd="/tmp/program {args}",
    ),
    RuntimeConfig(
        language="java",
        version="21.0.0",
        aliases=["jdk"],
        image="vbase-java-runner",
        extension=".java",
        compiled=True,
        compile_cmd="javac -d /tmp {file}",
        run_cmd="java -cp /tmp {classname} {args}",
    ),
]


def get_runtime_by_language(language: str) -> Optional[RuntimeConfig]:
    """Get runtime config by language name or alias"""
    language_lower = language.lower()
    for runtime in RUNTIMES:
        if runtime.language == language_lower or language_lower in runtime.aliases:
            return runtime
    return None


def get_all_runtimes() -> List[RuntimeConfig]:
    """Get all available runtimes"""
    return RUNTIMES


# Default security configuration
DEFAULT_SECURITY = SecurityConfig()
