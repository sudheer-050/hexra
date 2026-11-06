"""Face lock logic, tested with FAKE face fingerprints (the real face models are not needed for the logic)."""
import numpy as np

from hexra.face_lock import FaceLock, load_admin, normalize_rows, save_admin

rng = np.random.default_rng(0)


def person(seed):
    return normalize_rows(np.random.default_rng(seed).normal(size=128))[0]


def noisy(v, amount=0.25, seed=1):
    return normalize_rows(v + np.random.default_rng(seed).normal(0, amount / np.sqrt(128), 128))[0]


ADMIN, STRANGER = person(10), person(20)


class FakeFaces:
    """Stands in for the camera + face models: each 'frame' is just the list of fingerprints visible in it."""

    def __call__(self, frame):
        return [(emb, 0.99, (0, 0, 100, 100)) for emb in frame]


def lock(**kw):
    enrolled = np.stack([noisy(ADMIN, 0.2, s) for s in range(8)])         # several enrolment samples
    return FaceLock(FakeFaces(), enrolled, threaded=False, check_every_s=0.0, **kw)


class Frame(list):
    def copy(self):
        return Frame(self)


def test_the_admin_is_recognised_and_a_stranger_is_not():
    fl = lock()
    fl.submit(Frame([noisy(ADMIN, 0.3, 99)]), 1.0)
    assert fl.allowed(1.0) and "ADMIN" in fl.describe(1.0)
    fl2 = lock()
    fl2.submit(Frame([STRANGER]), 1.0)
    assert not fl2.allowed(1.0) and "not the admin" in fl2.describe(1.0)


def test_nobody_in_view_is_locked_by_default():
    fl = lock()
    fl.submit(Frame([]), 1.0)
    assert not fl.allowed(1.0) and "no face" in fl.describe(1.0)
    assert not lock().allowed(1.0)                                        # never seen anyone yet


def test_admin_stays_allowed_for_the_grace_period_then_locks():
    fl = lock(grace_s=3.0)
    fl.submit(Frame([noisy(ADMIN, 0.2, 5)]), 10.0)
    fl.submit(Frame([]), 11.0)                                            # looked away
    assert fl.allowed(12.5)
    assert not fl.allowed(13.5)                                           # more than 3 s since the admin was seen


def test_a_stranger_alone_never_unlocks_even_after_the_admin_left():
    fl = lock(grace_s=3.0)
    fl.submit(Frame([noisy(ADMIN, 0.2, 5)]), 10.0)
    fl.submit(Frame([STRANGER]), 11.0)
    assert fl.allowed(11.5)                                               # the admin was here 1.5 s ago
    fl.submit(Frame([STRANGER]), 14.0)
    assert not fl.allowed(14.0)


def test_admin_with_a_stranger_beside_them_is_allowed():
    fl = lock()
    fl.submit(Frame([STRANGER, noisy(ADMIN, 0.25, 7)]), 5.0)
    assert fl.allowed(5.0) and fl.faces == 2


def test_lenient_mode_only_blocks_when_a_stranger_is_in_view():
    fl = lock(require_face=False)
    assert fl.allowed(1.0)                                                # nobody seen: allowed (camera may aim at the hands)
    fl.submit(Frame([STRANGER]), 2.0)
    assert not fl.allowed(2.5)
    assert fl.allowed(6.0)                                                # the stranger left more than grace_s ago


def test_similar_but_different_people_are_kept_apart_by_the_threshold():
    u = np.random.default_rng(321).normal(size=128)
    u = u - np.dot(u, ADMIN) * ADMIN
    u /= np.linalg.norm(u)
    lookalike = 0.25 * ADMIN + np.sqrt(1 - 0.25 ** 2) * u                 # a relative: exactly 0.25 similar to the admin
    assert abs(float(np.dot(ADMIN, lookalike)) - 0.25) < 1e-4
    fl = lock()
    fl.submit(Frame([lookalike]), 1.0)
    assert not fl.allowed(1.0)


def test_checks_are_rate_limited_and_the_threaded_worker_never_blocks():
    enrolled = np.stack([noisy(ADMIN, 0.2, s) for s in range(4)])
    slow_calls = []

    def slow(frame):
        slow_calls.append(1)
        import time
        time.sleep(0.15)
        return [(noisy(ADMIN, 0.2, 9), 0.99, (0, 0, 1, 1))]

    fl = FaceLock(slow, enrolled, check_every_s=0.0, threaded=True)
    import time
    start = time.perf_counter()
    for i in range(50):
        fl.submit(Frame([1]), float(i) * 0.001)                           # the control loop hands pictures over
    assert time.perf_counter() - start < 0.05                             # ...without ever waiting for the analysis
    time.sleep(0.5)
    fl.close()
    assert 1 <= len(slow_calls) < 10                                      # busy worker skipped most pictures
    assert fl.allowed(0.05)


def test_enrolment_file_round_trip_and_nothing_but_numbers(tmp_path):
    path = str(tmp_path / "admin.npz")
    assert load_admin(path) is None
    save_admin(path, np.stack([ADMIN, noisy(ADMIN, 0.3, 4)]))
    loaded = load_admin(path)
    assert loaded.shape == (2, 128) and np.allclose(np.linalg.norm(loaded, axis=1), 1.0, atol=1e-5)
    with np.load(path) as f:
        assert set(f.files) == {"embeddings", "created"}                  # no images stored
