import re
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _extract_service_block(compose_content: str, service_name: str) -> str:
    """Extract the YAML configuration block for a given top-level service."""
    # Find service start: indentation of 2 spaces: "  <service_name>:"
    pattern = rf"(?m)^  {service_name}:\s*$"
    match = re.search(pattern, compose_content)
    assert match is not None, f"Service '{service_name}' not found in docker-compose.yml"

    start_pos = match.end()
    # Find next section at indentation level <= 2 (or end of file)
    next_section = re.search(r"(?m)^(?:  [a-zA-Z0-9_\-]+:|networks:|volumes:)", compose_content[start_pos:])
    if next_section:
        end_pos = start_pos + next_section.start()
        return compose_content[start_pos:end_pos]
    return compose_content[start_pos:]


def _extract_logging_options(service_block: str) -> dict:
    """Extract logging driver and options from a service block."""
    logging_match = re.search(r"logging:\s*\n((?:\s{6,}.*\n)+)", service_block)
    assert logging_match is not None, "Missing 'logging:' block in service definition"

    logging_lines = logging_match.group(1)

    driver_match = re.search(r'driver:\s*["\']?([a-zA-Z0-9_\-]+)["\']?', logging_lines)
    max_size_match = re.search(r'max-size:\s*["\']?([a-zA-Z0-9_\-]+)["\']?', logging_lines)
    max_file_match = re.search(r'max-file:\s*["\']?([a-zA-Z0-9_\-]+)["\']?', logging_lines)

    return {
        "driver": driver_match.group(1) if driver_match else None,
        "max_size": max_size_match.group(1) if max_size_match else None,
        "max_file": max_file_match.group(1) if max_file_match else None,
    }


def test_docker_compose_file_exists():
    """Verify docker-compose.yml is present in the project root."""
    assert COMPOSE_FILE.is_file(), f"Expected docker-compose.yml at {COMPOSE_FILE}"


def test_backend_container_logging_configuration():
    """Verify backend service is configured with json-file driver, 10m max-size, and 3 max-file."""
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    backend_block = _extract_service_block(content, "backend")

    log_config = _extract_logging_options(backend_block)
    assert log_config["driver"] == "json-file", f"Expected driver 'json-file', got {log_config['driver']}"
    assert log_config["max_size"] == "10m", f"Expected max-size '10m', got {log_config['max_size']}"
    assert log_config["max_file"] == "3", f"Expected max-file '3', got {log_config['max_file']}"


def test_frontend_container_logging_configuration():
    """Verify frontend service is configured with json-file driver, 5m max-size, and 3 max-file."""
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    frontend_block = _extract_service_block(content, "frontend")

    log_config = _extract_logging_options(frontend_block)
    assert log_config["driver"] == "json-file", f"Expected driver 'json-file', got {log_config['driver']}"
    assert log_config["max_size"] == "5m", f"Expected max-size '5m', got {log_config['max_size']}"
    assert log_config["max_file"] == "3", f"Expected max-file '3', got {log_config['max_file']}"


def test_essential_container_topology_preservation():
    """Verify essential services, healthchecks, networks, volumes, and dependencies remain preserved."""
    content = COMPOSE_FILE.read_text(encoding="utf-8")

    # 1. Services existence
    backend_block = _extract_service_block(content, "backend")
    frontend_block = _extract_service_block(content, "frontend")

    # 2. Network topology
    assert "datapulse_network:" in content
    assert "driver: bridge" in content
    assert "datapulse_network" in backend_block
    assert "datapulse_network" in frontend_block

    # 3. Persistent volume topology
    assert "datapulse_insights_data:" in content
    assert "datapulse_insights_data:/app/ai_agent/backend/data" in backend_block

    # 4. Service dependency (frontend depends on healthy backend)
    assert "depends_on:" in frontend_block
    assert "backend:" in frontend_block
    assert "condition: service_healthy" in frontend_block

    # 5. Health checks
    assert "healthcheck:" in backend_block
    assert "http://127.0.0.1:8001/health" in backend_block
    assert "healthcheck:" in frontend_block
    assert "http://127.0.0.1/" in frontend_block
