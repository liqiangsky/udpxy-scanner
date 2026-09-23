'''
Migration script from SQLite to PostgreSQL
Usage: python migrate_sqlite_to_pg.py <sqlite_db_path>
Env vars: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Tables: config, host, subscription, parameter
Columns renamed from camelCase to snake_case before insert (idempotent).
'''
import sqlite3
import os
import sys
import psycopg2

# One-time column renames: camelCase -> snake_case
_RENAMES = [
    ('config', 'dataSource', 'data_source'),
    ('config', 'templateRegion', 'template_region'),
    ('config', 'templateOperator', 'template_operator'),
    ('config', 'templateTargetName', 'template_target_name'),
    ('config', 'templateTargetAddress', 'template_target_address'),
    ('config', 'createdAt', 'created_at'),
    ('config', 'updatedAt', 'updated_at'),
    ('subscription', 'fetchCron', 'fetch_cron'),
    ('subscription', 'lastFetchAt', 'last_fetch_at'),
    ('subscription', 'createdAt', 'created_at'),
    ('subscription', 'updatedAt', 'updated_at'),
    ('cache', 'sourceType', 'source_type'),
    ('cache', 'geoRegion', 'geo_region'),
    ('cache', 'geoOperator', 'geo_operator'),
    ('cache', 'createdAt', 'created_at'),
    ('cache', 'updatedAt', 'updated_at'),
    ('host', 'sourceType', 'source_type'),
    ('host', 'sourceName', 'source_name'),
    ('host', 'geoRegion', 'geo_region'),
    ('host', 'geoOperator', 'geo_operator'),
    ('host', 'channelName', 'channel_name'),
    ('host', 'createdAt', 'created_at'),
    ('host', 'updatedAt', 'updated_at'),
]


def migrate(sqlite_path):
    print(f'[INFO] Reading SQLite: {sqlite_path}')
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    pg_host = os.getenv('PGHOST', 'db')
    pg_port = os.getenv('PGPORT', '5432')
    pg_database = os.getenv('PGDATABASE', 'udpxy')
    pg_user = os.getenv('PGUSER', 'udpxy')
    pg_password = os.getenv('PGPASSWORD', 'udpxy123')

    print(f'[INFO] Connecting to PostgreSQL: {pg_host}:{pg_port}/{pg_database}')
    pg_conn = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        dbname=pg_database,
        user=pg_user,
        password=pg_password
    )
    pg_cur = pg_conn.cursor()

    # Ensure snake_case columns (idempotent: skip when target name already exists)
    print('[INFO] Ensuring snake_case columns...')
    for table, old, new in _RENAMES:
        pg_cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name=%s AND column_name=%s",
            (table, new))
        if pg_cur.fetchone()[0]:
            print(f'  [SKIP] {table}.{new} already exists')
            continue
        pg_cur.execute(f'ALTER TABLE {table} RENAME COLUMN "{old}" TO {new}')
        print(f'  [OK] {table}: {old} -> {new}')

    try:
        # Migrate config table
        print('\n=== Migrating config table ===')
        sqlite_cursor.execute('SELECT * FROM config')
        config_rows = sqlite_cursor.fetchall()
        print(f'Read {len(config_rows)} config records')

        for row in config_rows:
            pg_cur.execute('''
                INSERT INTO config (
                    id, name, data_source, template_region, template_operator,
                    template_target_name, template_target_address, enabled,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            ''', (
                row['id'], row['name'], row['dataSource'], row['templateRegion'],
                row['templateOperator'], row['templateTargetName'],
                row['templateTargetAddress'], row['enabled'],
                row['createdAt'], row['updatedAt']
            ))
        print(f'[OK] Config table migration completed')

        # Migrate host table
        print('\n=== Migrating host table ===')
        sqlite_cursor.execute('SELECT * FROM host')
        host_rows = sqlite_cursor.fetchall()
        print(f'Read {len(host_rows)} host records')

        for row in host_rows:
            pg_cur.execute('''
                INSERT INTO host (
                    id, host, ip, port, source_type, source_name,
                    region, operator, geo_region, geo_operator,
                    delay, protocol, target, channel_name,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            ''', (
                row['id'], row['host'], row['ip'], row['port'],
                row['sourceType'], row['sourceName'],
                row['region'], row['operator'], row['geoRegion'], row['geoOperator'],
                row['delay'], row['protocol'], row['target'], row['channelName'],
                row['createdAt'], row['updatedAt']
            ))
        print(f'[OK] Host table migration completed')

        # Migrate subscription table
        print('\n=== Migrating subscription table ===')
        sqlite_cursor.execute('SELECT * FROM subscription')
        sub_rows = sqlite_cursor.fetchall()
        print(f'Read {len(sub_rows)} subscription records')

        for row in sub_rows:
            pg_cur.execute('''
                INSERT INTO subscription (
                    id, name, uid, url, type, enabled,
                    fetch_cron, last_fetch_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            ''', (
                row['id'], row['name'], row['uid'], row['url'],
                row['type'] if 'type' in row.keys() else '',
                row['enabled'],
                row['fetchCron'], row['lastFetchAt'],
                row['createdAt'], row['updatedAt']
            ))
        print(f'[OK] Subscription table migration completed')

        # Migrate parameter table (key-value, overwrite existing keys)
        print('\n=== Migrating parameter table ===')
        sqlite_cursor.execute('SELECT key, value FROM parameter')
        param_rows = sqlite_cursor.fetchall()
        print(f'Read {len(param_rows)} parameter records')

        for row in param_rows:
            pg_cur.execute('''
                INSERT INTO parameter (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            ''', (row['key'], row['value']))
        print(f'[OK] Parameter table migration completed')

        pg_conn.commit()

        # 序列校正：数据带显式 id 插入后，PG 自增序列不会自动跟进，
        # 不重置的话后续 INSERT 会撞主键（duplicate key ... xxx_pkey）
        print('\n=== Syncing id sequences ===')
        pg_cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "AND column_default LIKE 'nextval(%)'")
        for table_name, column_name in pg_cur.fetchall():
            pg_cur.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                (table_name, column_name))
            seq_name = pg_cur.fetchone()[0]
            if not seq_name:
                continue
            pg_cur.execute(
                "SELECT setval(%s::regclass, COALESCE((SELECT MAX({col}) FROM {tbl}), 0))".format(
                    col=column_name, tbl=table_name),
                (seq_name,))
            print(f'  [OK] {table_name}.{column_name} -> {pg_cur.fetchone()[0]}')
        pg_conn.commit()

        print('\n[SUCCESS] All data migration completed!')

    except Exception as e:
        pg_conn.rollback()
        print(f'[ERROR] Migration failed: {e}')
        raise
    finally:
        sqlite_conn.close()
        pg_cur.close()
        pg_conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python migrate_sqlite_to_pg.py <sqlite_db_path>')
        sys.exit(1)
    migrate(sys.argv[1])
