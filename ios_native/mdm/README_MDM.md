# Managed app configuration

Appen kan lese administrert konfigurasjon fra MDM gjennom `com.apple.configuration.managed`.

Bruk `ManagedAppConfig.example.plist` som mal når dere vil styre disse verdiene sentralt:

- `ServerURL`
- `AllowedHosts`
- `DisplayName`
- `SupportEmail`
- `BiometricRelockEnabled`
- `RelockAfterSeconds`
- `PinnedCertificateSHA256`

Tips:

1. Legg først inn grunnoppsett i `AppConfig.plist`.
2. La MDM overstyre produksjonsverdier per miljø eller enhetsgruppe.
3. Legg inn to sertifikat-hasher ved planlagt sertifikatrotasjon for å unngå avbrudd.
4. Ikke lagre persondata i managed configuration. Bruk kun teknisk oppsett.
