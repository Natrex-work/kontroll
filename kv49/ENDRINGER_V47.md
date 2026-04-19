# Endringer i v47

- Strammet inn ekstern HTTP-klient mot gis.fiskeridir.no med større connection pool og retry.
- La inn korttids-cache for bbox-baserte kartlag-responser på server.
- Begrenset klient-side parallell henting av kartlag for å redusere belastning.
- La inn tydelig oppstartsvarsel dersom KV_DB_PATH fortsatt peker til lokal appmappe i produksjon.
