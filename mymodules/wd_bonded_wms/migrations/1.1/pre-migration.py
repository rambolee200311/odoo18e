def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.bonded_customs_file')")
    if not cr.fetchone()[0]:
        return

    cr.execute('ALTER TABLE bonded_customs_file ADD COLUMN IF NOT EXISTS bonded_inbound_id integer')
    cr.execute('ALTER TABLE bonded_customs_file ADD COLUMN IF NOT EXISTS bonded_outbound_id integer')

    cr.execute("SELECT to_regclass('public.bonded_inbound')")
    if cr.fetchone()[0]:
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bonded_inbound' AND column_name = 't1_customs_file_id'
            )
        """)
        if cr.fetchone()[0]:
            cr.execute("""
                UPDATE bonded_customs_file AS customs_file
                   SET bonded_inbound_id = inbound.id
                  FROM bonded_inbound AS inbound
                 WHERE inbound.t1_customs_file_id = customs_file.id
                   AND customs_file.bonded_inbound_id IS NULL
            """)

    cr.execute("SELECT to_regclass('public.bonded_outbound')")
    if cr.fetchone()[0]:
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bonded_outbound' AND column_name = 'customs_file_id'
            )
        """)
        if cr.fetchone()[0]:
            cr.execute("""
                UPDATE bonded_customs_file AS customs_file
                   SET bonded_outbound_id = outbound.id
                  FROM bonded_outbound AS outbound
                 WHERE outbound.customs_file_id = customs_file.id
                   AND customs_file.bonded_outbound_id IS NULL
            """)
