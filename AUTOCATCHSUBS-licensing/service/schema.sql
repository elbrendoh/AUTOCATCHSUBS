-- Product-specific, authoritative one-device ledger. Never store plaintext codes.
CREATE TABLE IF NOT EXISTS seats (
  id TEXT PRIMARY KEY,
  code_hash TEXT NOT NULL UNIQUE,
  generation INTEGER NOT NULL DEFAULT 1 CHECK(generation > 0),
  state TEXT NOT NULL DEFAULT 'FREE' CHECK(state IN ('FREE','ACTIVE','REVOKED')),
  hwid TEXT NOT NULL DEFAULT '',
  computer TEXT NOT NULL DEFAULT '',
  profile TEXT NOT NULL DEFAULT '',
  alias TEXT NOT NULL DEFAULT '',
  activated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), sequence INTEGER NOT NULL);
INSERT OR IGNORE INTO metadata VALUES(1,0);
CREATE TABLE IF NOT EXISTS blocks (
  id TEXT NOT NULL, generation INTEGER NOT NULL, PRIMARY KEY(id,generation)
);
CREATE TABLE IF NOT EXISTS attempts (
  bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL
);
-- A spent code is never released or reassigned, including through Admin.
CREATE TRIGGER IF NOT EXISTS immutable_code
BEFORE UPDATE OF code_hash,generation ON seats
WHEN NEW.code_hash!=OLD.code_hash OR NEW.generation!=OLD.generation
BEGIN SELECT RAISE(ABORT,'Activation codes cannot be rotated or reused'); END;
CREATE TRIGGER IF NOT EXISTS immutable_device
BEFORE UPDATE OF hwid ON seats
WHEN OLD.hwid!='' AND NEW.hwid!=OLD.hwid
BEGIN SELECT RAISE(ABORT,'Activation device cannot be reassigned'); END;
CREATE TRIGGER IF NOT EXISTS spent_code
BEFORE UPDATE OF state ON seats
WHEN (OLD.state!='FREE' AND NEW.state='FREE') OR (OLD.state='REVOKED' AND NEW.state!='REVOKED')
BEGIN SELECT RAISE(ABORT,'Consumed or revoked codes remain consumed'); END;
