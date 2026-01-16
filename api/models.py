"""
Pydantic models for vbase-rce API - Compatible with Piston API v2
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FileEncoding(str, Enum):
    UTF8 = "utf8"
    BASE64 = "base64"
    HEX = "hex"


class File(BaseModel):
    """A file to be executed"""

    name: Optional[str] = Field(
        default=None, description="Filename, random if not provided"
    )
    content: str = Field(..., description="File content")
    encoding: Optional[FileEncoding] = Field(
        default=FileEncoding.UTF8, description="Content encoding"
    )


class ExecuteRequest(BaseModel):
    """Request body for code execution - Piston API v2 compatible"""

    language: str = Field(..., description="Language name or alias")
    version: str = Field(..., description="SemVer version selector")
    files: List[File] = Field(..., min_length=1, description="Files to execute")
    stdin: Optional[str] = Field(default="", description="Standard input")
    args: Optional[List[str]] = Field(
        default_factory=list, description="Command line arguments"
    )
    run_timeout: Optional[int] = Field(
        default=10000, description="Run timeout in milliseconds"
    )
    compile_timeout: Optional[int] = Field(
        default=10000, description="Compile timeout in milliseconds"
    )
    run_memory_limit: Optional[int] = Field(
        default=-1, description="Run memory limit in bytes (-1 for default)"
    )
    compile_memory_limit: Optional[int] = Field(
        default=-1, description="Compile memory limit in bytes (-1 for default)"
    )


class RunResult(BaseModel):
    """Result from a run/compile stage"""

    stdout: str = Field(..., description="Standard output")
    stderr: str = Field(..., description="Standard error")
    output: str = Field(..., description="Combined stdout and stderr")
    code: Optional[int] = Field(..., description="Exit code, null if signal")
    signal: Optional[str] = Field(default=None, description="Signal name, null if code")


class ExecuteResponse(BaseModel):
    """Response body for code execution - Piston API v2 compatible"""

    language: str = Field(..., description="Language name (not alias)")
    version: str = Field(..., description="Runtime version")
    run: RunResult = Field(..., description="Run stage results")
    compile: Optional[RunResult] = Field(
        default=None, description="Compile stage results (if applicable)"
    )


class Runtime(BaseModel):
    """Available runtime information"""

    language: str = Field(..., description="Language name")
    version: str = Field(..., description="Runtime version")
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    runtime: Optional[str] = Field(
        default=None, description="Runtime name if alternative exists"
    )


class ErrorResponse(BaseModel):
    """Error response"""

    message: str = Field(..., description="Error message")
