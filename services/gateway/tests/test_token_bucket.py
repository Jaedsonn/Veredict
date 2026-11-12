import pytest

from gateway_service.adapters.token_bucket import InMemoryTokenBucket
from gateway_service.domain import RateDecision, RateLimit
from gateway_service.routes import LOGIN_LIMIT, REGISTER_LIMIT, RESEND_LIMIT

from .conftest import FakeClock


@pytest.fixture
def bucket(fake_clock: FakeClock) -> InMemoryTokenBucket:
    return InMemoryTokenBucket(clock=fake_clock)


async def _burst(bucket: InMemoryTokenBucket, key: str, limit: RateLimit, n: int) -> list[bool]:
    return [(await bucket.hit(key, limit)).allowed for _ in range(n)]


async def test_login_burst_then_refill(bucket: InMemoryTokenBucket, fake_clock: FakeClock) -> None:
    assert await _burst(bucket, "ip|h", LOGIN_LIMIT, 5) == [True] * 5
    assert await bucket.hit("ip|h", LOGIN_LIMIT) == RateDecision(False, 12)

    fake_clock.advance(11.9)
    assert await bucket.hit("ip|h", LOGIN_LIMIT) == RateDecision(False, 1)

    fake_clock.advance(0.1)
    assert (await bucket.hit("ip|h", LOGIN_LIMIT)).allowed
    assert not (await bucket.hit("ip|h", LOGIN_LIMIT)).allowed

    fake_clock.advance(60)
    assert await _burst(bucket, "ip|h", LOGIN_LIMIT, 6) == [True] * 5 + [False]


async def test_register_eleventh_waits_six_seconds(bucket: InMemoryTokenBucket) -> None:
    assert await _burst(bucket, "ip", REGISTER_LIMIT, 10) == [True] * 10
    assert await bucket.hit("ip", REGISTER_LIMIT) == RateDecision(False, 6)


async def test_denial_does_not_consume(bucket: InMemoryTokenBucket, fake_clock: FakeClock) -> None:
    await _burst(bucket, "ip", REGISTER_LIMIT, 10)

    waits = []
    for _ in range(10):
        waits.append((await bucket.hit("ip", REGISTER_LIMIT)).retry_after)
        fake_clock.advance(0.5)

    assert waits == [6, 6, 5, 5, 4, 4, 3, 3, 2, 2]
    fake_clock.advance(1)
    assert (await bucket.hit("ip", REGISTER_LIMIT)).allowed


async def test_keys_and_policies_are_independent(bucket: InMemoryTokenBucket) -> None:
    await _burst(bucket, "1.1.1.1", REGISTER_LIMIT, 10)

    assert not (await bucket.hit("1.1.1.1", REGISTER_LIMIT)).allowed
    assert (await bucket.hit("2.2.2.2", REGISTER_LIMIT)).allowed
    assert (await bucket.hit("1.1.1.1", RESEND_LIMIT)).allowed
    assert (await bucket.hit("1.1.1.1", LOGIN_LIMIT)).allowed


@pytest.mark.parametrize("elapsed", [0.0, 0.3, 5.5, 11.99])
async def test_retry_after_is_integer_rounded_up(
    bucket: InMemoryTokenBucket, fake_clock: FakeClock, elapsed: float
) -> None:
    await _burst(bucket, "k", LOGIN_LIMIT, 5)
    fake_clock.advance(elapsed)

    decision = await bucket.hit("k", LOGIN_LIMIT)

    assert isinstance(decision.retry_after, int)
    assert decision.retry_after >= 1
    assert decision.retry_after == max(1, -int(-(12 - elapsed) // 1))


async def test_refilled_buckets_are_dropped(
    bucket: InMemoryTokenBucket, fake_clock: FakeClock
) -> None:
    for ip in ("a", "b", "c"):
        await bucket.hit(ip, REGISTER_LIMIT)
    assert len(bucket) == 3

    fake_clock.advance(60)
    await bucket.hit("d", REGISTER_LIMIT)

    assert len(bucket) == 1


async def test_partially_refilled_bucket_is_kept(
    bucket: InMemoryTokenBucket, fake_clock: FakeClock
) -> None:
    await _burst(bucket, "a", REGISTER_LIMIT, 10)
    fake_clock.advance(30)
    await bucket.hit("b", REGISTER_LIMIT)

    assert len(bucket) == 2


async def test_max_keys_evicts_least_recently_used(fake_clock: FakeClock) -> None:
    bucket = InMemoryTokenBucket(clock=fake_clock, max_keys=3)
    for ip in ("a", "b", "c"):
        await _burst(bucket, ip, REGISTER_LIMIT, 10)
    # "a" volta a ser o mais recente; o mais antigo passa a ser "b"
    assert not (await bucket.hit("a", REGISTER_LIMIT)).allowed

    await bucket.hit("d", REGISTER_LIMIT)

    assert len(bucket) == 3
    assert (await bucket.hit("b", REGISTER_LIMIT)).allowed
    assert not (await bucket.hit("a", REGISTER_LIMIT)).allowed


async def test_default_clock_is_monotonic() -> None:
    bucket = InMemoryTokenBucket()

    assert (await bucket.hit("k", LOGIN_LIMIT)).allowed
