"""Keeps the user-space PostgreSQL cluster alive across pipeline runs."""
import time
import pgserver

srv = pgserver.get_server('/home/sandbox/aisignal-pipeline/data/pg')
with open('/home/sandbox/aisignal-pipeline/data/pg.uri', 'w') as f:
    f.write(srv.get_uri())
print("postgres up:", srv.get_uri(), flush=True)
while True:
    time.sleep(3600)
