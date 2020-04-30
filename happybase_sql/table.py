from contextlib import contextmanager
import datetime

from sqlalchemy import (
    and_,
    cast,
    Column,
    func,
    MetaData,
    select,
    String,
    Table as SQLAlchemyTable,
)
from sqlalchemy.dialects.postgresql import insert, JSONB


def _get_table_for_name(name):
    """
    Generate and return a generic SQLAlchemyTable for the table [name].

    All tables have the same set of columns.
    """
    return SQLAlchemyTable(
        name,
        MetaData(),

        # The row key in a HBase table
        Column('key', String, primary_key=True, nullable=False),

        # All data in a HBase row is stored under this column
        Column('data', JSONB, nullable=False),
    )


def _row_to_key(row):
    """
    Ensure the row is lowercase.
    """
    return str(row).lower()


def _parse_filter(filter_):
    """
    Attempt to parse a [filter_] string into a labelled dict of filter parameters.

    E.g. for filter "SingleColumnValueFilter('e', 'insta', >, 'binary:0', true, true)" it should
    return a result like:
    {
        'column_family': 'e',
        'column_name': 'insta',
        'operator': '>',
        'value': '0',
        'filter_if_missing': True,
        'latest_version_only': True,
    }
    """
    if not filter_:
        return None

    # Strip the method and parenthesis from the string, tokenize the result and strip all
    # surrounding whitespace and qoutes
    stripped = filter_[filter_.find('(') + 1:filter_.rfind(')')]
    tok = [it.strip().replace('\'', '').replace('"', '') for it in stripped.split(',')]

    return {
        'column_family': tok[0],
        'column_qualifier': tok[1],
        'comparator': tok[2],
        'value': tok[3].replace('binary:', ''),
        'filter_if_missing': len(tok) > 4 and tok[4].lower() == 'true',
        'latest_version_only': len(tok) <= 5 or tok[5].lower() == 'true',
    }


def _check_filter(data, filter_):
    """
    Returns True if the [data] payload parses the [filter_], False otherwise.

    Will attempt to parse values to be compared to the correct (and same) type before comparison.
    E.g. '2018-04-04T07:10:49.812255+00:00' will be parsed to a datetime object.

    If the comparison values can't be detected as the same type, they will be compared as is
    (usually strings).
    """
    if filter_['comparator'] not in ['=', '!=', '<', '>', '<=', '>=']:
        raise ValueError('Unknown comparator: {}'.format(filter_['comparator']))

    data_key = '{}:{}'.format(filter_['column_family'], filter_['column_qualifier'])

    if data_key not in data:
        return not filter_['filter_if_missing']

    lhs = str(data[data_key])
    rhs = str(filter_['value'])
    comparator = filter_['comparator']

    if lhs.isdigit() and rhs.isdigit():
        lhs = int(lhs)
        rhs = int(rhs)
    else:
        try:
            # If the dates have a sub-second or timezone, just discard them, because CBF.
            lhs_datetime = datetime.datetime.strptime(lhs[:19], '%Y-%m-%dT%H:%M:%S')
            rhs_datetime = datetime.datetime.strptime(rhs[:19], '%Y-%m-%dT%H:%M:%S')

            lhs = lhs_datetime
            rhs = rhs_datetime
        except ValueError:  # noqa
            # Failure to convert either lhs or rhs, they are not datetime strings
            pass

    if comparator == '=' and lhs == rhs:
        return True
    if comparator == '!=' and lhs != rhs:
        return True
    if comparator == '<' and lhs < rhs:
        return True
    if comparator == '>' and lhs > rhs:
        return True
    if comparator == '<=' and lhs <= rhs:
        return True
    if comparator == '>=' and lhs >= rhs:
        return True
    return False


class Batch(object):
    """
    (Almost) drop-in replacement for the happybase.Batch class.
    """

    def __init__(self, table):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Batch
        """
        self._table = table
        # Operations are inserted into the list by the delete() and put() methods, where each item
        # is of the form:
        # (
        #   operation: str,
        #   (
        #       args: Sequence,
        #       kwargs: Dict,
        #   )
        # )
        self._operations = []

    def delete(self, row, columns=None, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Batch.delete
        """
        self._operations.append(
            (
                'delete',
                (
                    (row,),
                    {'columns': columns},
                ),
            )
        )

    def put(self, row, data, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Batch.put
        """
        self._operations.append(
            (
                'put',
                (
                    (row, data,),
                    {},
                ),
            )
        )

    def send(self):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Batch.send
        """
        for operation, (args, kwargs) in self._operations:
            if operation == 'delete':
                self._table.delete(*args, **kwargs)
            elif operation == 'put':
                self._table.put(*args, **kwargs)
            else:
                raise ValueError('Unknown operation type: {}'.format(operation))


class Table(object):
    """
    A limited drop-in replacement for the happybase Table class. The purpose of this class is to
    replicate the functionality of the happybase Table class but using a relational database as the
    backend, rather than HBase.
    """

    def __init__(self, name, session_cls, *_):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table
        """
        self._table = _get_table_for_name(name)
        self._session_cls = session_cls

    def batch(self, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.batch
        """
        return Batch(self)

    def delete(self, row, columns=None, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.delete
        """
        with self._session() as session:
            result = session.query(self._table).filter_by(key=_row_to_key(row)).first()

            if not result:
                return

            if columns:
                new_data = result.data.copy()
                for key in columns:
                    if key in new_data:
                        del new_data[key]
                session.execute(
                    self._table.update().where(
                        self._table.c.key == _row_to_key(row)
                    ).values(
                        key=_row_to_key(row),
                        data=new_data,
                    )
                )
            else:
                session.execute(
                    self._table.delete().where(self._table.c.key == _row_to_key(row))
                )

    def put(self, row, data, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.put
        """
        with self._session() as session:
            insert_statement = insert(
                self._table,
            ).values(
                key=_row_to_key(row),
                data=data,
            ).on_conflict_do_update(
                index_elements=['key'],
                set_={
                    'data': self._table.c.data + cast(data, JSONB),
                },
            )
            session.execute(insert_statement)

    def row(self, row, columns=None, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.row
        """
        with self._session() as session:

            result = session.execute(
                self._select(
                    columns=columns,
                ).where(
                    self._table.c.key == _row_to_key(row),
                ),
            )

            data = result.fetchone()

            return data[1] if data else {}

    def rows(self, rows, columns=None, batch_size=100, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.rows
        """
        keys = [_row_to_key(row) for row in rows]

        with self._session() as session:

            result = session.connection(
                execution_options={'stream_results': True},
            ).execute(
                self._select(
                    columns=columns,
                ).where(
                    self._table.c.key.in_(keys),
                ),
            )

            while True:
                chunk = result.fetchmany(batch_size)
                if not chunk:
                    break
                for key, data in chunk:
                    yield (key, data)

    def scan(self, row_start=None, row_stop=None, row_prefix=None, columns=None, filter=None,
             limit=None, batch_size=100, **__):
        """
        https://happybase.readthedocs.io/en/latest/api.html#happybase.Table.scan
        """
        if not row_prefix and not (row_start and row_stop):
            self.log.warning(
                'Either both \'row_start\' and \'row_stop\', or \'row_prefix\' should be given, '
                'otherwise the entire table will be scanned!',
            )

        filters = []
        if row_start:
            filters.append(self._table.c.key >= _row_to_key(row_start))
        if row_stop:
            filters.append(self._table.c.key < _row_to_key(row_stop))
        if row_prefix:
            filters.append(self._table.c.key.like('{}%'.format(row_prefix)))

        parsed_filter = _parse_filter(filter)

        with self._session() as session:

            result = session.connection(
                execution_options={'stream_results': True},
            ).execute(
                self._select(
                    columns=columns,
                ).where(
                    and_(*filters),
                ).order_by(
                    self._table.c.key.asc(),
                ),
            )

            yielded_count = 0
            should_continue = True
            while True:
                chunk = result.fetchmany(batch_size)
                if not chunk:
                    break

                for key, data in chunk:
                    if isinstance(limit, int) and yielded_count >= limit:
                        should_continue = False
                        break

                    if parsed_filter:
                        # There is probably some clever way to work the filter into the SQL query,
                        # but it is easier and probably good enough to do this client side.
                        if not _check_filter(data, parsed_filter):
                            continue

                    yielded_count += 1
                    yield (key, data)

                if not should_continue:
                    break

    def _select(self, columns):
        """
        Generates a select statement for this table.

        [columns] is a list of column names that will be returned in the data, columns in the
        table that aren't in the list will not be retrieved. If [columns] is None or empty,
        then all columns are retrieved.
        """
        data_column = self._table.c.data

        if columns:
            data_column = select(
                [func.jsonb_object_agg(Column('key'), Column('value'))],
            ).select_from(
                func.jsonb_each(self._table.c.data),
            ).where(
                Column('key').in_(columns),
            ).label(
                'data',
            )

        return select(
            [self._table.c.key, data_column],
        ).select_from(
            self._table,
        )

    @contextmanager
    def _session(self):
        """Provide a transactional scope around a series of operations."""
        session = self._session_cls()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
