import threading, time
from domain.state_store import SessionLockManager
from conversation.message_buffer import MessageSessionBuffer


def test_second_acquire_blocks_while_first_holds():
    m = SessionLockManager(default_timeout=0.3)
    assert m.acquire("s")
    assert m.acquire("s", timeout=0.2) is False  # no silent reset: really serialized
    m.release("s")
    assert m.acquire("s", timeout=0.2) is True
    m.release("s")


def test_force_reset_cannot_let_stale_release_free_new_lock():
    m = SessionLockManager(default_timeout=0.3)
    got = []
    started, go = threading.Event(), threading.Event()

    def old_turn():
        assert m.acquire("s"); started.set(); go.wait(2); m.release("s")

    t = threading.Thread(target=old_turn); t.start(); started.wait(2)
    m.force_reset("s")                      # explicit user cancel
    assert m.acquire("s", timeout=0.2)      # new turn holds the fresh lock
    go.set(); t.join()                      # stale thread releases ITS lock, not ours
    assert m.acquire("s", timeout=0.2) is False
    m.release("s")


def test_buffer_folds_superseded_message():
    b = MessageSessionBuffer(window_seconds=5)
    b.add_message("s", "i want media rolls")
    assert b.get_combined_prompt("s", "and magenta ink") == "i want media rolls\nand magenta ink"
    assert b.get_combined_prompt("s", "next") == "next"  # consumed once
