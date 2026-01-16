"""
Code execution engine for vbase-rce
Handles container lifecycle, code execution, and output capture
"""

import base64
import os
import re
import tempfile
from typing import Optional, Tuple

import docker
import docker.errors
from config import DEFAULT_SECURITY, RuntimeConfig, get_runtime_by_language
from models import ExecuteRequest, ExecuteResponse, File, FileEncoding, RunResult


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
        cmd_template: str,
        filename: str,
        args: list[str],
        content: Optional[str] = None,
        runtime: Optional[RuntimeConfig] = None,
    ) -> str:
        """Build the command to execute"""
        args_str = " ".join(f'"{arg}"' for arg in args) if args else ""

        cmd = cmd_template.format(
            file=f"/code/{filename}",
            args=args_str,
            classname=self._extract_java_classname(content)
            if content and runtime and runtime.language == "java"
            else "",
        )

        return cmd.strip()

    def _run_container(
        self,
        image: str,
        command: str,
        temp_dir: str,
        stdin: str = "",
        timeout: int = 10,
        memory_limit: str = "128m",
    ) -> Tuple[str, str, int, Optional[str]]:
        """
        Run a container with the given command and security constraints
        Returns: (stdout, stderr, exit_code, signal)
        """
        container = None

        try:
            # Prepare container configuration with security constraints
            container_config = {
                "image": image,
                "command": ["/bin/sh", "-c", command],
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
        Execute code and return Piston-compatible response
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
                compile_cmd = self._build_command(
                    runtime.compile_cmd, main_file, [], main_content, runtime
                )
                run_cmd = self._build_command(
                    runtime.run_cmd,
                    main_file,
                    request.args or [],
                    main_content,
                    runtime,
                )

                # Combine compile and run: compile && run
                # This way the binary stays in /tmp within the same container
                combined_cmd = f"{compile_cmd} && {run_cmd}"

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
