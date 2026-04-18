# Fiskerikontroll – iOS native pakke v41

Denne pakken bygger videre på produksjonsversjonen og legger til en egen native iOS-del for intern distribusjon.

## Innhold

- SwiftUI-basert iPhone/iPad-app i `ios_native/`
- Xcode-prosjekt (`KontrollOgOppsynNative.xcodeproj`)
- backupspesifikasjon for XcodeGen (`project.yml`)
- appikonsett generert fra eksisterende appikon
- `AppConfig.plist` for serveradresse og tillatte domener
- biometrisk gjenlåsing med Face ID / kode
- håndtering av dokumentnedlasting fra webdelen til delingsark i iOS
- sperre for topplastenavigasjon til andre domener enn de som er konfigurert
- eksportprofiler for ad hoc og enterprise-eksempel

## Viktig begrensning

Det er ikke mulig å produsere en signert `.ipa` i dette Linux-miljøet fordi sluttbygging, signering og arkivering for iOS må gjøres i Xcode på macOS. Derfor er pakken laget som en ferdig kildepakke for Xcode med dokumentasjon for intern distribusjon.

## Anbefalt distribusjonsmåte

- pilot / få enheter: ad hoc / registrerte enheter
- bred intern utrulling: private app i Apple Business Manager
- direkte intern distribusjon uten App Store Connect: kun hvis virksomheten allerede har Apple Developer Enterprise Program og faktisk kvalifiserer for det

## Filer å åpne først

- `ios_native/README_IOS_NATIVE.md`
- `ios_native/KontrollOgOppsynNative.xcodeproj`
- `ios_native/KontrollOgOppsynNative/AppConfig.plist`
