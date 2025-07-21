from asyncpg.exceptions import ConnectionDoesNotExistError
from sqlalchemy.exc import DBAPIError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential


def with_retry():
    return retry(
        retry=retry_if_exception_type((ConnectionDoesNotExistError, DBAPIError)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(5),
        reraise=True,
    )
