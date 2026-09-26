from src.harness.state import State

def test_state_init():
    state = State(task="Test task")
    assert state.task == "Test task"
    assert state.iteration == 0
    assert state.status == "init"
