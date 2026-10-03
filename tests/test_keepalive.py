import threading

from slice_and_dice.keepalive import KeepAlive


def test_pings_until_stopped():
    pinged = threading.Event()
    calls = []

    def ping():
        calls.append(1)
        if len(calls) >= 3:
            pinged.set()

    keepalive = KeepAlive(0.01, ping)
    keepalive.start()
    assert pinged.wait(timeout=5)
    keepalive.stop()
    keepalive._thread.join(timeout=5)
    assert not keepalive._thread.is_alive()


def test_failing_pings_do_not_kill_the_thread(caplog):
    survived = threading.Event()
    calls = []

    def ping():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("network down")
        survived.set()

    keepalive = KeepAlive(0.01, ping)
    keepalive.start()
    assert survived.wait(timeout=5)
    keepalive.stop()
    assert "keep-alive ping failed" in caplog.text
