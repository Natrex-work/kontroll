import SwiftUI

struct RootView: View {
    @StateObject private var webStore = WebViewStore()
    @EnvironmentObject private var networkMonitor: NetworkMonitor
    @EnvironmentObject private var appLock: AppLockController

    var body: some View {
        Group {
            if AppConfig.shared.needsSetup {
                ConfigErrorView()
            } else {
                ZStack {
                    SecureWebView(store: webStore)
                        .ignoresSafeArea(edges: .bottom)

                    if appLock.isLocked {
                        SessionLockView(
                            isAuthenticating: appLock.isAuthenticating,
                            errorMessage: appLock.errorMessage,
                            unlockAction: appLock.unlock
                        )
                    }
                }
                .background(Color(.systemBackground))
                .safeAreaInset(edge: .top, spacing: 0) {
                    VStack(spacing: 0) {
                        if !networkMonitor.isConnected {
                            banner(
                                text: "Ingen nettverkstilkobling. Appen trenger tilgang til den sikre \(AppConfig.shared.displayName)-serveren.",
                                symbol: "wifi.slash"
                            )
                        }
                        if let errorMessage = webStore.errorMessage {
                            HStack(spacing: 12) {
                                Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                                    .font(.footnote)
                                    .foregroundStyle(.primary)
                                Spacer(minLength: 8)
                                Button("Prøv igjen") {
                                    webStore.loadHome(force: true)
                                }
                                .buttonStyle(.bordered)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .background(Color.yellow.opacity(0.22))
                        }
                        if webStore.isLoading {
                            ProgressView(value: max(webStore.estimatedProgress, 0.05), total: 1)
                                .progressViewStyle(.linear)
                                .tint(.accentColor)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 6)
                                .background(Color(.secondarySystemBackground))
                        }
                    }
                }
                .sheet(item: $webStore.downloadItem) { item in
                    ShareSheet(activityItems: [item.url])
                }
                .onAppear {
                    webStore.loadHomeIfNeeded()
                    appLock.bootstrapIfNeeded()
                }
            }
        }
    }

    @ViewBuilder
    private func banner(text: String, symbol: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
            Text(text)
                .font(.footnote)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .foregroundStyle(.primary)
        .background(Color.orange.opacity(0.18))
    }
}
