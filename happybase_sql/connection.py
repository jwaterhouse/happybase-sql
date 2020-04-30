from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    MetaData,
)
from sqlalchemy.orm import sessionmaker

from .table import Table


class Connection(object):
    """
    (Almost) drop-in replacement for the happybase.Connection class.
    """

    def __init__(
            self,
            host=None,
            table_prefix=None,
            table_prefix_separator=b'_',
            session_cls=None,
            **__
    ):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Connection

        Note: host refers to the full SQL database URL (e.g. postgresql://localhost:5432/hbase)
        """
        self._table_prefix = table_prefix
        self._table_prefix_separator = table_prefix_separator
        if session_cls:
            self._session_cls = session_cls
        else:
            engine = create_engine(host)
            self._session_cls = sessionmaker(bind=engine)

    def close(self):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Connection.close
        """
        pass

    def open(self):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Connection.open
        """
        pass

    def table(self, name, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Connection.table
        """
        if self._table_prefix is not None:
            name = '{}{}{}'.format(
                self._table_prefix,
                self._table_prefix_separator,
                name,
            )
        return Table(name, self._session_cls)

    def tables(self):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Connection.tables
        """
        meta = MetaData()
        meta.reflect(bind=self._session_cls.kw['bind'])
        return sorted([it.name for it in meta.sorted_tables])


class ConnectionPool(object):
    """
    (Almost) drop-in replacement for the happybase.ConnectionPool class.
    """

    def __init__(self, size, host, **kwargs):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.ConnectionPool
        """
        engine = create_engine(
            host,
            pool_size=size,
        )
        self._session_cls = sessionmaker(bind=engine)
        self._connection_kwargs = kwargs

    @contextmanager
    def connection(self, *_):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.ConnectionPool.connection
        """
        yield Connection(session_cls=self._session_cls, **self._connection_kwargs)
