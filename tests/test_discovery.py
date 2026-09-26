import json
from src.harness.verification.test_runner import TestRunner


def test_discovery_explicit_configured_command(tmp_path):
    runner = TestRunner(
        str(tmp_path),
        test_command="python -m unittest discover",
        explicit_test_command="python -m unittest discover"
    )
    disc = runner.discover_test_command()
    assert disc["command"] == "python -m unittest discover"
    assert disc["source"] == "explicit_config"
    assert disc["confidence"] == "high"


def test_discovery_makefile(tmp_path):
    (tmp_path / "Makefile").write_text("test:\n\t@echo 'running make test'\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "make test"
    assert disc["source"] == "Makefile"
    assert disc["confidence"] == "high"


def test_discovery_node_package_json(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "my-app",
        "scripts": {"test": "jest --coverage"}
    }))
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "npm test"
    assert disc["source"] == "package.json"
    assert disc["confidence"] == "high"


def test_discovery_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "pytest"
    assert disc["source"] == "pyproject.toml"
    assert disc["confidence"] == "high"


def test_discovery_python_pytest_ini(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "pytest"
    assert disc["source"] == "pytest.ini"
    assert disc["confidence"] == "high"


def test_discovery_python_setup_cfg(tmp_path):
    (tmp_path / "setup.cfg").write_text("[tool:pytest]\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "pytest"
    assert disc["source"] == "setup.cfg"
    assert disc["confidence"] == "high"


def test_discovery_rust_cargo(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'demo'\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "cargo test"
    assert disc["source"] == "Cargo.toml"
    assert disc["confidence"] == "high"


def test_discovery_go(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/app\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "go test ./..."
    assert disc["source"] == "go.mod"
    assert disc["confidence"] == "high"


def test_discovery_maven(tmp_path):
    (tmp_path / "pom.xml").write_text("<project></project>\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "mvn test"
    assert disc["source"] == "pom.xml"
    assert disc["confidence"] == "high"


def test_discovery_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("plugins { id 'java' }\n")
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "gradle test"
    assert disc["source"] == "build.gradle"
    assert disc["confidence"] == "high"


def test_discovery_fallback(tmp_path):
    runner = TestRunner(str(tmp_path))
    disc = runner.discover_test_command()
    assert disc["command"] == "make test"
    assert disc["source"] == "fallback"
    assert disc["confidence"] == "low"
