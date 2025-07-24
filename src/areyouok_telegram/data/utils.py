from asyncpg.exceptions import ConnectionDoesNotExistError
from asyncpg.exceptions import InterfaceError
from sqlalchemy.exc import DBAPIError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_chain
from tenacity import wait_fixed
from tenacity import wait_random_exponential


def with_retry():
    return retry(
        retry=retry_if_exception_type((ConnectionDoesNotExistError, DBAPIError, InterfaceError)),
        wait=wait_chain(*[wait_fixed(0.5) for _ in range(2)] + [wait_random_exponential(multiplier=0.5, max=5)]),
        stop=stop_after_attempt(5),
        reraise=True,
    )
