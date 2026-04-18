import Foundation
import LocalAuthentication
import SwiftUI

@MainActor
final class AppLockController: ObservableObject {
    @Published var isLocked: Bool
    @Published var isAuthenticating = false
    @Published var errorMessage: String?

    private let config: AppConfig
    private var lastBackgroundAt: Date?
    private var bootstrapped = false

    init(config: AppConfig = .shared) {
        self.config = config
        self.isLocked = config.biometricRelockEnabled
    }

    func bootstrapIfNeeded() {
        guard !bootstrapped else { return }
        bootstrapped = true
        guard config.biometricRelockEnabled else {
            isLocked = false
            return
        }
        unlock()
    }

    func handleScenePhase(_ phase: ScenePhase) {
        switch phase {
        case .active:
            if !bootstrapped {
                bootstrapIfNeeded()
                return
            }
            guard config.biometricRelockEnabled else { return }
            if shouldRelock {
                isLocked = true
                unlock()
            }
        case .background:
            lastBackgroundAt = Date()
        default:
            break
        }
    }

    private var shouldRelock: Bool {
        guard config.biometricRelockEnabled else { return false }
        guard let lastBackgroundAt else { return isLocked }
        return Date().timeIntervalSince(lastBackgroundAt) >= config.relockAfterSeconds
    }

    func unlock() {
        guard config.biometricRelockEnabled else {
            isLocked = false
            return
        }
        let context = LAContext()
        var authError: NSError?
        let reason = "Lås opp \(config.displayName)"
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &authError) else {
            isLocked = false
            errorMessage = nil
            return
        }
        isAuthenticating = true
        errorMessage = nil
        context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { [weak self] success, evaluationError in
            DispatchQueue.main.async {
                guard let self else { return }
                self.isAuthenticating = false
                self.isLocked = !success
                if success {
                    self.errorMessage = nil
                } else if let laError = evaluationError as? LAError, laError.code == .userCancel {
                    self.errorMessage = nil
                } else {
                    self.errorMessage = "Kunne ikke verifisere bruker. Prøv igjen."
                }
            }
        }
    }
}
