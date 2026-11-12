import psycopg2

conn = psycopg2.connect(
    host='aws-0-ap-south-1.pooler.supabase.com',
    port=5432,
    database='postgres',
    user='postgres.rngzfxcurkfyfwwcsups',
    password='Adichowdary@720'
)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_postgres' AND pid <> pg_backend_pid()")
print('Terminated connections')
conn.close()