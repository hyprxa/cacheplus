import asyncio
import concurrent.futures
import time
from unittest.mock import MagicMock

import pytest

from cacheplus import async_cache_value, cache_value
from cacheplus.exceptions import (
    UnhashableParamError,
    UnserializableReturnValueError,
)


def test_can_cache_pickleable_value():
    """Tests that a cached function is only called once."""
    mock = MagicMock(return_value="pickleable")

    @cache_value()
    def call_mock():
        return mock()

    result_1 = call_mock()
    result_2 = call_mock()
    assert result_1 == result_2
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_can_cache_pickleable_value_async():
    """Tests that a cached async function is only called once."""
    mock = MagicMock(return_value="pickleable")

    @async_cache_value()
    async def call_mock():
        return mock()

    result_1 = await call_mock()
    result_2 = await call_mock()
    assert result_1 == result_2
    mock.assert_called_once()


def test_cannot_cache_non_pickleable_value():
    """Tests that non-pickleable return values cannot be cached."""
    import tempfile

    @cache_value()
    def not_picklable():
        with tempfile.TemporaryFile() as tf:
            return tf

    with pytest.raises(UnserializableReturnValueError):
        not_picklable()

    try:
        not_picklable()
    except UnserializableReturnValueError as e:
        assert isinstance(e.__cause__, TypeError)


@pytest.mark.asyncio
async def test_cannot_cache_non_pickleable_value_async():
    """Tests that non-pickleable return values cannot be cached."""
    import tempfile

    @async_cache_value()
    async def not_picklable():
        with tempfile.TemporaryFile() as tf:
            return tf

    with pytest.raises(UnserializableReturnValueError):
        await not_picklable()

    try:
        await not_picklable()
    except UnserializableReturnValueError as e:
        assert isinstance(e.__cause__, TypeError)


def test_concurrent_calls_are_not_serialized():
    """Tests that concurrent calls to a cached function are not serialized (a
    function called with same arguments can run more than once).
    """
    mock = MagicMock(return_value="pickleable")

    @cache_value()
    def call_mock():
        time.sleep(0.1)
        return mock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futs = (executor.submit(call_mock), executor.submit(call_mock))
        concurrent.futures.wait(futs)

    result_1 = futs[0].result()
    result_2 = futs[1].result()
    assert result_1 == result_2
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_concurrent_calls_are_not_serialized_async():
    """Tests that concurrent calls to a cached function are not serialized (a
    function called with same arguments can run more than once).
    """
    mock = MagicMock(return_value="pickleable")

    @async_cache_value()
    async def call_mock():
        await asyncio.sleep(0.1)
        return mock()

    coro_1, coro_2 = (call_mock(), call_mock())
    result_1, result_2 = await asyncio.gather(coro_1, coro_2)

    assert result_1 == result_2
    assert mock.call_count == 2


def test_concurrent_calls_can_be_serialized():
    """Tests that concurrent calls to a cached function can be serialized."""
    mock = MagicMock(return_value="pickleable")

    @cache_value(serialize=True)
    def call_mock():
        time.sleep(0.1)
        return mock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futs = (executor.submit(call_mock), executor.submit(call_mock))
        concurrent.futures.wait(futs)

    result_1 = futs[0].result()
    result_2 = futs[1].result()
    assert result_1 == result_2
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_calls_can_be_serialized_async():
    """Tests that concurrent calls to a cached function can be serialized."""
    mock = MagicMock(return_value="pickleable")

    @async_cache_value(serialize=True)
    async def call_mock():
        await asyncio.sleep(0.1)
        return mock()

    coro_1, coro_2 = (call_mock(), call_mock())
    result_1, result_2 = await asyncio.gather(coro_1, coro_2)

    assert result_1 == result_2
    mock.assert_called_once()


def test_cache_value_cannot_wrap_coroutine():
    """Tests that wrapping a coroutine in ``cache_value`` raises a ``TypeError``."""
    with pytest.raises(TypeError):

        @cache_value()
        async def call():
            pass


def test_async_cache_value_must_wrap_coroutine():
    """Tests that wrapping a non-coroutine in ``async_cache_value`` raises a ``TypeError``."""
    with pytest.raises(TypeError):

        @async_cache_value()
        def call():
            pass


def test_value_expiration():
    """Tests that values expire."""
    mock = MagicMock(return_value="pickleable")

    @cache_value(expires_in=1)
    def call_mock():
        return mock()

    result_1 = call_mock()
    time.sleep(1.01)
    result_2 = call_mock()
    assert result_1 == result_2
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_value_expiration_async():
    """Tests that values expire."""
    mock = MagicMock(return_value="pickleable")

    @async_cache_value(expires_in=1)
    async def call_mock():
        return mock()

    result_1 = await call_mock()
    await asyncio.sleep(1.01)
    result_2 = await call_mock()
    assert result_1 == result_2
    assert mock.call_count == 2


def test_type_encoders():
    """Tests that types which are not natively hashable can be hashed by providing
    a callable that encodes the type.
    """
    from http.client import HTTPConnection

    mock = MagicMock(return_value="pickleable")

    @cache_value()
    def call_fail(conn: HTTPConnection):
        pass

    def encode_conn(conn: HTTPConnection):
        return f"{conn.host}:{conn.port}"

    type_encoders = {HTTPConnection: encode_conn}

    @cache_value(type_encoders=type_encoders)
    def call_success(conn: HTTPConnection):
        return mock(conn)

    conn = HTTPConnection("google.com")
    conn.connect()
    try:
        with pytest.raises(UnhashableParamError):
            call_fail(conn)
        result_1 = call_success(conn)
        result_2 = call_success(conn)
    finally:
        conn.close()

    assert result_1 == result_2
    mock.assert_called_once_with(conn)


@pytest.mark.asyncio
async def test_type_encoders_async():
    """Tests that types which are not natively hashable can be hashed by providing
    a callable that encodes the type.
    """
    from http.client import HTTPConnection

    mock = MagicMock(return_value="pickleable")

    @async_cache_value()
    async def call_fail(conn: HTTPConnection):
        pass

    def encode_conn(conn: HTTPConnection):
        return f"{conn.host}:{conn.port}"

    type_encoders = {HTTPConnection: encode_conn}

    @async_cache_value(type_encoders=type_encoders)
    async def call_success(conn: HTTPConnection):
        return mock(conn)

    conn = HTTPConnection("google.com")
    conn.connect()
    try:
        with pytest.raises(UnhashableParamError):
            await call_fail(conn)
        result_1 = await call_success(conn)
        result_2 = await call_success(conn)
    finally:
        conn.close()

    assert result_1 == result_2
    mock.assert_called_once_with(conn)
