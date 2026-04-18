# Endringer i v42 – sikkerhetsherdet produksjonspakke

- fjernet demo-/eksempelinformasjon fra pakke og tekster
- lagt inn CSRF-beskyttelse i skjemaer, eksport og JSON-endepunkter
- lagt inn Trusted Host-kontroll, HSTS, CSP og øvrige sikkerhetsheadere
- fjernet offentlig tilgang til opplastede filer og genererte dokumenter
- lagt inn strengere filopplastingskontroll og signaturvalidering
- lagt inn innloggingsbegrensning og tidsstyrt sesjonskontroll
- oppdatert service worker til bare å cache statiske filer
- beholdt kartforbedringer, manuell posisjon og redigerbart løpenummer
