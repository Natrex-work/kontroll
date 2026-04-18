import SwiftUI

@main
struct KontrollOgOppsynNativeApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var networkMonitor = NetworkMonitor()
    @StateObject private var appLock = AppLockController()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(networkMonitor)
                .environmentObject(appLock)
                .preferredColorScheme(.light)
        }
        .onChange(of: scenePhase) { newPhase in
            appLock.handleScenePhase(newPhase)
        }
    }
}
