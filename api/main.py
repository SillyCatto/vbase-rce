"""
vbase-rce API - Remote Code Execution Engine
"""

from contextlib import asynccontextmanager
from typing import Optional

import docker
import docker.errors
from config import get_all_runtimes, get_runtime_by_language
from executor import CodeExecutor, ExecutionError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models import ErrorResponse, ExecuteRequest, ExecuteResponse, Runtime

# Initialize Docker client and executor
docker_client: Optional[docker.DockerClient] = None
executor: Optional[CodeExecutor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global docker_client, executor

    # Startup
    docker_client = docker.from_env()
    executor = CodeExecutor(docker_client)

    # Check Docker connection
    try:
        docker_client.ping()
        print("✓ Connected to Docker daemon")
    except Exception as e:
        print(f"✗ Failed to connect to Docker: {e}")
        raise

    # List available runner images
    print("\nAvailable runner images:")
    for runtime in get_all_runtimes():
        try:
            docker_client.images.get(runtime.image)
            print(f"  ✓ {runtime.image} ({runtime.language} {runtime.version})")
        except docker.errors.ImageNotFound:
            print(f"  ✗ {runtime.image} (not built)")

    yield

    # Shutdown
    if docker_client:
        docker_client.close()


app = FastAPI(
    title="vbase-rce",
    description="Remote Code Execution Engine - Piston API v2 Compatible",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


# --- Piston API v2 Compatible Endpoints ---


@app.get("/api/v2/runtimes", response_model=list[Runtime])
async def list_runtimes():
    """
    List all available runtimes
    Piston API v2 compatible
    """
    if not docker_client:
        raise HTTPException(
            status_code=503, detail={"message": "Service not initialized"}
        )

    runtimes = []
    for rt in get_all_runtimes():
        # Only include runtimes that have their images built
        try:
            docker_client.images.get(rt.image)
            runtimes.append(
                Runtime(
                    language=rt.language,
                    version=rt.version,
                    aliases=rt.aliases,
                    runtime=rt.runtime,
                )
            )
        except docker.errors.ImageNotFound:
            continue

    return runtimes


@app.post(
    "/api/v2/execute",
    response_model=ExecuteResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def execute_code(request: ExecuteRequest):
    """
    Execute code in an isolated container
    Piston API v2 compatible
    """
    if not executor:
        raise HTTPException(
            status_code=503, detail={"message": "Service not initialized"}
        )

    # Validate language
    runtime = get_runtime_by_language(request.language)
    if not runtime:
        raise HTTPException(
            status_code=400,
            detail={"message": f"Unsupported language: {request.language}"},
        )

    # Validate files
    if not request.files or len(request.files) == 0:
        raise HTTPException(
            status_code=400, detail={"message": "At least one file is required"}
        )

    try:
        result = await executor.execute(request)
        return result
    except ExecutionError as e:
        raise HTTPException(status_code=400, detail={"message": e.message})
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"message": f"Internal error: {str(e)}"}
        )


# --- Additional utility endpoints ---


@app.get("/api/v2/runtimes/{language}")
async def get_runtime(language: str):
    """Get details for a specific runtime"""
    runtime = get_runtime_by_language(language)
    if not runtime:
        raise HTTPException(
            status_code=404, detail={"message": f"Language not found: {language}"}
        )

    return Runtime(
        language=runtime.language,
        version=runtime.version,
        aliases=runtime.aliases,
        runtime=runtime.runtime,
    )
