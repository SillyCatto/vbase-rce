# vbase-rce

A lightweight Remote Code Execution (RCE) engine for VBase

## Features

- **Piston API v2 Compatible**: Drop-in replacement for Piston API
- **Multiple Language Support**: Python, JavaScript (Node.js), C, C++, Java
- **Lightweight**: Alpine-based container images
- **Secure**: Memory limits, CPU limits, network isolation, read-only filesystem, process limits
- **Simple Deployment**: Single docker-compose command

## Supported Languages

| Language   | Version | Aliases                        |
|------------|---------|--------------------------------|
| Python     | 3.12.0  | python3, py                    |
| JavaScript | 20.0.0  | js, node, node-js              |
| C          | 13.2.0  | gcc                            |
| C++        | 13.2.0  | cpp, g++, cplusplus            |
| Java       | 21.0.0  | jdk                            |

## Quick Start

### 1. Build and Start

```bash
# Build all images and start the API
docker-compose up --build -d

# View logs
docker-compose logs -f rce-api
```

### 2. Test the API

```bash
# List available runtimes
curl http://localhost:8000/api/v2/runtimes

# Execute Python code
curl -X POST http://localhost:8000/api/v2/execute \
  -H "Content-Type: application/json" \
  -d '{
    "language": "python",
    "version": "3.12.0",
    "files": [{"content": "print(\"Hello, World!\")"}]
  }'

# Execute JavaScript
curl -X POST http://localhost:8000/api/v2/execute \
  -H "Content-Type: application/json" \
  -d '{
    "language": "javascript",
    "version": "20.0.0",
    "files": [{"content": "console.log(\"Hello from Node.js!\")"}]
  }'

# Execute C++ with compilation
curl -X POST http://localhost:8000/api/v2/execute \
  -H "Content-Type: application/json" \
  -d '{
    "language": "cpp",
    "version": "13.2.0",
    "files": [{"content": "#include <iostream>\nint main() { std::cout << \"Hello C++!\" << std::endl; return 0; }"}]
  }'
```

## API Endpoints

### GET /api/v2/runtimes

List all available language runtimes.

**Response:**
```json
[
  {
    "language": "python",
    "version": "3.12.0",
    "aliases": ["python3", "py"]
  }
]
```

### POST /api/v2/execute

Execute code in an isolated container.

**Request:**
```json
{
  "language": "python",
  "version": "3.12.0",
  "files": [
    {
      "name": "main.py",
      "content": "print('Hello!')"
    }
  ],
  "stdin": "",
  "args": [],
  "run_timeout": 10000,
  "run_memory_limit": -1
}
```

**Response:**
```json
{
  "language": "python",
  "version": "3.12.0",
  "run": {
    "stdout": "Hello!\n",
    "stderr": "",
    "output": "Hello!\n",
    "code": 0,
    "signal": null
  }
}
```

## Security Features

Each code execution runs in an isolated Docker container with:

- **Memory Limit**: 128 MB default, 256 MB max
- **CPU Limit**: 50% of one CPU core
- **Timeout**: 10 seconds default, 30 seconds max
- **Network**: Completely disabled
- **Filesystem**: Read-only root filesystem
- **Process Limit**: Max 64 processes
- **Capabilities**: All dropped
- **Privileges**: No new privileges allowed

## Project Structure

```
vbase-rce/
├── api/
│   ├── Dockerfile       # API server container
│   ├── main.py          # FastAPI application
│   ├── models.py        # Pydantic models
│   ├── config.py        # Runtime configuration
│   ├── executor.py      # Code execution engine
│   └── requirements.txt # Python dependencies
├── runners/
│   ├── python/Dockerfile
│   ├── node/Dockerfile
│   ├── c/Dockerfile
│   ├── cpp/Dockerfile
│   └── java/Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Development

### Run locally without Docker (for API development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r api/requirements.txt

# Run the API (requires Docker daemon running)
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Build individual runner images

```bash
docker build -t vbase-python-runner ./runners/python
docker build -t vbase-node-runner ./runners/node
docker build -t vbase-c-runner ./runners/c
docker build -t vbase-cpp-runner ./runners/cpp
docker build -t vbase-java-runner ./runners/java
```

## Deployment (DigitalOcean)

1. Create a Droplet with Docker pre-installed
2. Clone this repository
3. Run `docker-compose up --build -d`
4. Configure firewall to allow port 8000
5. (Optional) Set up a reverse proxy with HTTPS

```bash
# On your DigitalOcean droplet
git clone <your-repo-url> vbase-rce
cd vbase-rce
docker-compose up --build -d
```

## License

MIT
