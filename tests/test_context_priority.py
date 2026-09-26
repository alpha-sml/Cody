from src.harness.context.context_manager import ContextManager


def test_task_pinned_file_survives_budget_eviction():
    cm = ContextManager(max_files=5)
    # Task mentions auth_service.py explicitly
    cm.set_task("Fix the token expiration bug in auth_service.py")

    # Add the task file
    cm.add_tool_result({
        "tool": "file_read",
        "args": {"path": "auth_service.py"},
        "result": {"content": "class AuthService: pass"}
    })
    assert "auth_service.py" in cm.relevant_files

    # Now add 10 other unrelated files
    for i in range(10):
        cm.add_tool_result({
            "tool": "file_read",
            "args": {"path": f"unrelated_{i}.py"},
            "result": {"content": f"data {i}"}
        })

    # Total files must not exceed 5
    assert len(cm.relevant_files) == 5
    # The high-priority task file auth_service.py MUST survive
    assert "auth_service.py" in cm.relevant_files
    assert "auth_service.py" in cm.file_contents


def test_symbol_relevant_file_has_higher_priority_than_incidental_reads():
    cm = ContextManager(max_files=3)
    cm.set_task("Implement TokenValidator verification")

    # File with matching symbol
    cm.add_file_content("validator.py", "class TokenValidator:\n    pass\n")

    # Two incidental reads
    cm.add_file_content("incidental1.py", "# no symbol")
    cm.add_file_content("incidental2.py", "# no symbol")
    assert len(cm.relevant_files) == 3

    # Add 4th incidental read - should evict one of incidental files, NOT validator.py
    cm.add_file_content("incidental3.py", "# no symbol")
    assert len(cm.relevant_files) == 3
    assert "validator.py" in cm.relevant_files


def test_search_results_and_mutations_prioritized_over_incidental():
    cm = ContextManager(max_files=3)

    # Incidental read
    cm.add_file_content("incidental.py", "data")

    # Mutated file
    cm.add_tool_result({
        "tool": "file_write",
        "args": {"path": "mutated.py", "content": "modified"},
        "result": {"status": "success"}
    })

    # Search result
    cm.add_tool_result({
        "tool": "file_search",
        "args": {"pattern": "needle"},
        "result": {"results": "matched.py:10:needle found\n"}
    })

    assert len(cm.relevant_files) == 3
    assert "mutated.py" in cm.relevant_files
    assert "matched.py" in cm.relevant_files

    # Add another incidental read
    cm.add_file_content("another_incidental.py", "data2")

    # incidental.py (priority 20) should be evicted before mutated.py (60) or matched.py (40)
    assert "mutated.py" in cm.relevant_files
    assert "matched.py" in cm.relevant_files
    assert "incidental.py" not in cm.relevant_files


def test_bounded_context_size():
    cm = ContextManager(max_files=10)
    huge_text = "x" * 20000
    cm.add_file_content("huge.txt", huge_text)
    # Content must be truncated at 10000 + indicator
    assert len(cm.file_contents["huge.txt"]) < 10100
    assert "...[TRUNCATED]" in cm.file_contents["huge.txt"]
