import SwiftUI

struct ConfigErrorView: View {
    private let config = AppConfig.shared

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Label("iOS-oppsettet er ikke ferdig konfigurert", systemImage: "gear.badge.xmark")
                        .font(.title3.weight(.semibold))
                    Text(config.setupSummary)
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Gjør dette før du bygger appen:")
                            .font(.headline)
                        Text("1. Åpne filen ios_native/KontrollOgOppsynNative/AppConfig.plist.")
                        Text("2. Sett ServerURL til den sikre HTTPS-adressen til Fiskerikontroll.")
                        Text("3. Oppdater AllowedHosts med samme domene og eventuelle underdomener som skal være lovlige i appen.")
                        Text("4. Bygg og signer appen på nytt i Xcode.")
                    }
                    .font(.body)
                    .padding()
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .padding()
            }
            .navigationTitle("Konfigurasjon mangler")
        }
    }
}
