"""Isolated state-machine demonstration, not a substitute for Worker race tests."""
def simulate():
    import sqlite3
    db=sqlite3.connect(':memory:')
    db.execute("CREATE TABLE seat(state TEXT, hwid TEXT)")
    db.execute("INSERT INTO seat VALUES('FREE',NULL)")
    def activate(hwid):
        db.execute("UPDATE seat SET state='ACTIVE',hwid=? WHERE state='FREE'",(hwid,))
        return db.execute("SELECT state='ACTIVE' AND hwid=? FROM seat",(hwid,)).fetchone()[0]==1
    try:
        assert activate('device-a')
        assert not activate('device-b')
        assert activate('device-a')
        db.execute("UPDATE seat SET state='REVOKED'")
        assert not activate('device-a') and not activate('device-b')
        assert db.execute('SELECT hwid FROM seat').fetchone()[0]=='device-a'
        return True
    finally:db.close()
