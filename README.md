# happybase-sql #

A (mostly) drop-in replacement for [happybase](https://happybase.readthedocs.io/en/latest/) that uses an SQL backend instead of HBase.

** Why would I want to use this? **

This project came about when I was working on a legacy project that used a HBase datastore. The HBase cluster became problematic, suffering from performance issues and was expensive to run. After wrestling with HBase for too long, I decided to migrate the data to SQL and wrote this replacement for the happybase library. It's mostly API compatible, so only needed a few minor changes to the code base to swap it in for happybase and thus avoid a lot of time-consuming refactoring. Depending how capital-B *Big Data* your requirements are, you might find (like I did) that the scale of HBase actually wasn't required, and an SQL DB was plenty big enough, much simpler to administer and a lot cheaper.

## Getting started ##

You'll need to create a table in your SQL database for each of your HBase tables.

*Note: currently only Postgres is supported*

Here's an example table definition, just replace `my_table_name` with the name of your table. Note the two indices, one for key uniqueness (which is the equivalent of the HBase row key), and the `varchar_pattern_ops` index. This is required to allow efficient prefix queries, a feature of HBase key lookups and scans. The data is stored in a JSONB column, where the keys of that JSON data are the HBase column names (e.g. 'cf:col').

```sql
CREATE TABLE public."my_table_name" (
	"key" varchar NOT NULL,
	"data" jsonb NOT NULL
);
CREATE UNIQUE INDEX my_table_name_key_idx ON public.my_table_name USING btree (key);
CREATE INDEX my_table_name_key_ops_idx ON public.my_table_name USING btree (key varchar_pattern_ops);
```

Install the happybase-sql package into your project:

```bash
pip install happybase-sql
```

Create a `Connection` or `ConnectionPool`. Note that the `host` argument is slightly different to `happybase`, it now refers to the *full* SQL database URL (including port). The port argument is ignored.

```python
from happybase_sql import ConnectionPool


connection_pool = ConnectionPool(size=3, host='postgresql://localhost:5432/hbase')

with connection_pool.connection() as connection:
    table = connection.table('my_table_name')
    table.put(
        row='abcd',
        data={
            'cf:col1': 'some data',
            'cf:col2': 'some more data',
        },
    )
    row = table.row('abcd')
    print(row)
```
