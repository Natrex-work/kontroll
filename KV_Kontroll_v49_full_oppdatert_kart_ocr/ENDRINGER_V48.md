# Endringer i v48

- Synkroniserte standardlagene mot det offentlige `fiskeridirWMS_fiskeri`-karttjenestelaget hos Fiskeridirektoratet, med korrigerte lag-ID-er for blant annet nullfiskeområder i Oslofjorden, Borgundfjorden, Breivikfjorden, Jenn egga/Malangsgrunnen og Storegga.
- Innførte ny cacheskjema-versjon for kartlag slik at gamle, feilaktige katalog- og geometri-cachefiler ikke brukes etter oppdatering.
- Utvidet lagkatalogen til også å hente `kystnaere_fiskeridata` når live-kilden svarer, slik at oversiktskartet kan vise mer av de aktuelle fiskeriområdene.
- Flyttet mobilknappene for `Tilbake` og `Videre` opp på samme linje som KV-logoen, og skjulte den store stegmenyen på mobil.
- Fjernet unødvendig live-henting av kartlag fra sider som ikke trenger kart, for å redusere belastning og minske risikoen for feil ved navigasjon til Hjem.
- Stopper geolokasjons-watch og kamerastream når brukeren forlater kontrollsiden, slik at appen oppfører seg roligere ved navigasjon.
