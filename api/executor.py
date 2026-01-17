"""
Code execution engine for vbase-rce
Handles container lifecycle, code execution, and output capture
"""

import asyncio
import base64
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

import docker
import docker.errors
from config import DEFAULT_SECURITY, RuntimeConfig, get_runtime_by_language
from models import ExecuteRequest, ExecuteResponse, File, FileEncoding, RunResult

# Maximum concurrent code executions (configurable via environment)
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))


class ExecutionError(Exception):
    """Custom exception for execution errors"""

    def __init__(self, message: str, code: int = 1):
        self.message = message
        self.code = code
        super().__init__(message)


class CodeExecutor:
    """
    Handles code execution in isolated Docker containers
    """

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        self.client = docker_client or docker.from_env()
        self.security = DEFAULT_SECURITY
        # Limit concurrent executions to prevent resource exhaustion
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        # Thread pool for running blocking Docker operations
        self.executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)

    def _decode_file_content(self, file: File) -> str:
        """Decode file content based on encoding"""
        if file.encoding == FileEncoding.BASE64:
            return base64.b64decode(file.content).decode("utf-8")
        elif file.encoding == FileEncoding.HEX:
            return bytes.fromhex(file.content).decode("utf-8")
        return file.content

    def _get_filename(self, file: File, runtime: RuntimeConfig, index: int) -> str:
        """Generate appropriate filename"""
        if file.name:
            # Ensure proper extension
            if not file.name.endswith(runtime.extension):
                return file.name + runtime.extension
            return file.name

        # For Java, we need to extract class name
        if runtime.language == "java":
            return f"Main{runtime.extension}"

        return f"main{runtime.extension}"

    def _extract_java_classname(self, content: str) -> str:
        """Extract the public class name from Java code"""
        match = re.search(r"public\s+class\s+(\w+)", content)
        if match:
            return match.group(1)
        return "Main"

    def _prepare_code_files(
        self, files: list[File], runtime: RuntimeConfig, temp_dir: str
    ) -> str:
        """Write code files to temp directory, return main file path"""
        main_file = "main"

        for i, file in enumerate(files):
            content = self._decode_file_content(file)
            filename = self._get_filename(file, runtime, i)
            filepath = os.path.join(temp_dir, filename)

            with open(filepath, "w") as f:
                f.write(content)

            if i == 0:
                main_file = filename

        return main_file

    def _build_command(
        self,
        cmd_template: list[str],
        filename: str,
        args: list[str],
        content: Optional[str] = None,
        runtime: Optional[RuntimeConfig] = None,
    ) -> list[str]:
        """
        Build the command to execute as a list (prevents shell injection)
        """
        result = []
        for part in cmd_template:
            if part == "{file}":
                result.append(f"/code/{filename}")
            elif part == "{classname}":
                classname = (
                    self._extract_java_classname(content)
                    if content and runtime and runtime.language == "java"
                    else ""
                )
                if classname:
                    result.append(classname)
            else:
                result.append(part)

        # Append args directly as separate elements (safe, no shell interpretation)
        if args:
            result.extend(args)

        return result

    def _shell_quote(self, arg: str) -> str:
        """
        Safely quote a string for shell usage.
        Uses single quotes and escapes any single quotes within.
        """
        import shlex

        return shlex.quote(arg)

    def _build_shell_command_for_compiled(
        self, compile_cmd: list[str], run_cmd: list[str]
    ) -> list[str]:
        """
        Build a shell command for compiled languages that chains compile && run.
        Each argument is properly quoted to prevent shell injection.
        Returns a command list that uses sh -c with safely quoted arguments.
        """
        # Quote each argument safely
        compile_str = " ".join(self._shell_quote(arg) for arg in compile_cmd)
        run_str = " ".join(self._shell_quote(arg) for arg in run_cmd)

        # Chain with && so run only happens if compile succeeds
        combined = f"{compile_str} && {run_str}"

        return ["/bin/sh", "-c", combined]

    def _run_container(
        self,
        image: str,
        command: list[str],
        temp_dir: str,
        stdin: str = "",
        timeout: int = 10,
        memory_limit: str = "128m",
    ) -> Tuple[str, str, int, Optional[str]]:
        """
        Run a container with the given command and security constraints.
        Command is passed as a list to prevent shell injection.
        Returns: (stdout, stderr, exit_code, signal)
        """
        container = None

        try:
            # Prepare container configuration with security constraints
            container_config = {
                "image": image,
                "command": command,  # Pass command list directly - no shell
                "volumes": {temp_dir: {"bind": "/code", "mode": "ro"}},
                "working_dir": "/code",
                "user": self.security.user,
                "detach": True,
                "stdin_open": bool(stdin),
                # Security constraints
                "network_disabled": self.security.network_disabled,
                "mem_limit": memory_limit,
                "memswap_limit": memory_limit,  # Prevent swap usage
                "nano_cpus": self.security.nano_cpus,
                "pids_limit": self.security.pids_limit,
                "cap_drop": self.security.cap_drop,
                "security_opt": self.security.security_opt,
                "read_only": self.security.read_only_rootfs,
                # Tmpfs for writable directories - exec needed for compiled binaries
                # Also include home directory for Go cache and other runtime caches
                "tmpfs": {
                    "/tmp": f"size={self.security.tmpfs_size},mode=1777,exec",
                    "/home/runner": f"size={self.security.tmpfs_size},mode=1777,exec",
                },
            }

            container = self.client.containers.create(**container_config)
            container.start()

            # If stdin is provided, attach and send it
            if stdin:
                sock = container.attach_socket(params={"stdin": True, "stream": True})
                sock._sock.sendall(stdin.encode("utf-8"))
                sock._sock.close()

            # Wait for container to finish with timeout
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", 1)

            # Capture output
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )

            # Check for OOM kill
            container.reload()
            if container.attrs.get("State", {}).get("OOMKilled", False):
                stderr += "\n[Process killed: Out of memory]"
                return stdout, stderr, 137, "SIGKILL"

            return stdout, stderr, exit_code, None

        except docker.errors.ContainerError as e:
            return "", str(e), e.exit_status, None

        except Exception as e:
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                # Kill the container on timeout
                if container:
                    try:
                        container.kill()
                    except Exception:
                        pass
                return (
                    "",
                    f"Execution timed out after {timeout} seconds",
                    -1,
                    "SIGKILL",
                )
            raise

        finally:
            # Always cleanup container
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _calculate_timeout(self, timeout_ms: Optional[int]) -> int:
        """Convert milliseconds to seconds, apply limits"""
        if timeout_ms is None or timeout_ms <= 0:
            return self.security.default_timeout

        timeout_sec = timeout_ms // 1000
        return min(timeout_sec, self.security.max_timeout)

    def _calculate_memory_limit(self, memory_bytes: Optional[int]) -> str:
        """Convert bytes to Docker memory limit string, apply limits"""
        if memory_bytes is None or memory_bytes <= 0:
            return self.security.default_memory_limit

        # Convert to MB
        memory_mb = memory_bytes // (1024 * 1024)
        max_mb = int(self.security.max_memory_limit.replace("m", ""))

        memory_mb = min(memory_mb, max_mb)
        memory_mb = max(memory_mb, 16)  # Minimum 16 MB

        return f"{memory_mb}m"

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """
        Execute code and return Piston-compatible response.
        Uses a semaphore to limit concurrent executions.
        """
        async with self.semaphore:
            # Run the blocking execution in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.executor, self._execute_sync, request
            )

    def _execute_sync(self, request: ExecuteRequest) -> ExecuteResponse:
        """
        Synchronous execution logic (runs in thread pool)
        """
        # Get runtime configuration
        runtime = get_runtime_by_language(request.language)
        if not runtime:
            raise ExecutionError(f"Unsupported language: {request.language}")

        # Check if image exists
        try:
            self.client.images.get(runtime.image)
        except docker.errors.ImageNotFound:
            raise ExecutionError(
                f"Runtime image not found: {runtime.image}. Please build the runner images first."
            )

        # Calculate limits
        run_timeout = self._calculate_timeout(request.run_timeout)
        compile_timeout = self._calculate_timeout(request.compile_timeout)
        run_memory = self._calculate_memory_limit(request.run_memory_limit)
        # Note: compile_memory_limit not used since we combine compile+run in single container

        compile_result = None

        with tempfile.TemporaryDirectory(prefix="vbase-rce-") as temp_dir:
            # Write code files
            main_file = self._prepare_code_files(request.files, runtime, temp_dir)
            main_content = self._decode_file_content(request.files[0])

            compile_result = None

            # Handle compiled languages - compile and run in same container
            if runtime.compiled and runtime.compile_cmd:
                compile_cmd_list = self._build_command(
                    runtime.compile_cmd, main_file, [], main_content, runtime
                )
                run_cmd_list = self._build_command(
                    runtime.run_cmd,
                    main_file,
                    request.args or [],
                    main_content,
                    runtime,
                )

                # For compiled languages, we need shell to chain compile && run
                # Build the command safely by properly quoting each argument
                combined_cmd = self._build_shell_command_for_compiled(
                    compile_cmd_list, run_cmd_list
                )

                stdout, stderr, code, signal = self._run_container(
                    image=runtime.image,
                    command=combined_cmd,
                    temp_dir=temp_dir,
                    stdin=request.stdin or "",
                    timeout=compile_timeout + run_timeout,  # Allow time for both
                    memory_limit=run_memory,
                )

                # For compiled languages, we can't easily separate compile vs run output
                # If there's an error, it could be compile or runtime
                run_result = RunResult(
                    stdout=stdout,
                    stderr=stderr,
                    output=stdout + stderr,
                    code=code,
                    signal=signal,
                )

                return ExecuteResponse(
                    language=runtime.language,
                    version=runtime.version,
                    run=run_result,
                    compile=None,  # Combined execution doesn't separate stages
                )

            # For interpreted languages - just run
            run_cmd = self._build_command(
                runtime.run_cmd, main_file, request.args or [], main_content, runtime
            )

            stdout, stderr, code, signal = self._run_container(
                image=runtime.image,
                command=run_cmd,
                temp_dir=temp_dir,
                stdin=request.stdin or "",
                timeout=run_timeout,
                memory_limit=run_memory,
            )

            run_result = RunResult(
                stdout=stdout,
                stderr=stderr,
                output=stdout + stderr,
                code=code,
                signal=signal,
            )

            return ExecuteResponse(
                language=runtime.language,
                version=runtime.version,
                run=run_result,
                compile=compile_result,
            )
