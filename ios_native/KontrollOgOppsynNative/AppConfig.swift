import Foundation

private enum ManagedDefaults {
    static let key = "com.apple.configuration.managed"

    static func read() -> [String: Any] {
        UserDefaults.standard.dictionary(forKey: key) ?? [:]
    }
}

struct AppConfig {
    let serverURL: URL
    let allowedHosts: [String]
    let displayName: String
    let biometricRelockEnabled: Bool
    let relockAfterSeconds: TimeInterval
    let supportEmail: String
    let pinnedCertificateSHA256: [String]
    let usesManagedConfiguration: Bool

    static let shared: AppConfig = {
        let bundled = loadBundledConfig()
        let managed = ManagedDefaults.read()
        let merged = bundled.merging(managed) { _, managedValue in managedValue }

        let serverURLString = stringValue(for: "ServerURL", in: merged) ?? AppConfig.fallback.serverURL.absoluteString
        let serverURL = URL(string: serverURLString) ?? AppConfig.fallback.serverURL
        let displayName = stringValue(for: "DisplayName", in: merged) ?? AppConfig.fallback.displayName
        let biometric = boolValue(for: "BiometricRelockEnabled", in: merged) ?? AppConfig.fallback.biometricRelockEnabled
        let relockSeconds = numberValue(for: "RelockAfterSeconds", in: merged) ?? AppConfig.fallback.relockAfterSeconds
        let supportEmail = stringValue(for: "SupportEmail", in: merged) ?? AppConfig.fallback.supportEmail
        var allowedHosts = stringArrayValue(for: "AllowedHosts", in: merged)
        if allowedHosts.isEmpty, let host = serverURL.host?.lowercased() {
            allowedHosts = [host]
        }
        let pinnedCertificateSHA256 = stringArrayValue(for: "PinnedCertificateSHA256", in: merged)
        return AppConfig(
            serverURL: serverURL,
            allowedHosts: allowedHosts,
            displayName: displayName,
            biometricRelockEnabled: biometric,
            relockAfterSeconds: max(0, relockSeconds),
            supportEmail: supportEmail,
            pinnedCertificateSHA256: pinnedCertificateSHA256,
            usesManagedConfiguration: !managed.isEmpty
        )
    }()

    static let fallback = AppConfig(
        serverURL: URL(string: "https://example.invalid")!,
        allowedHosts: ["example.invalid"],
        displayName: "Fiskerikontroll",
        biometricRelockEnabled: true,
        relockAfterSeconds: 30,
        supportEmail: "it@example.no",
        pinnedCertificateSHA256: [],
        usesManagedConfiguration: false
    )

    var needsSetup: Bool {
        guard let scheme = serverURL.scheme?.lowercased(), let host = serverURL.host?.lowercased() else {
            return true
        }
        if host == "example.invalid" {
            return true
        }
        if scheme == "https" {
            return false
        }
        return !["localhost", "127.0.0.1"].contains(host)
    }

    var setupSummary: String {
        let sourceText = usesManagedConfiguration ? "MDM-administrert konfigurasjon" : "AppConfig.plist"
        return "Konfigurer korrekt HTTPS-adresse for produksjonsmiljøet i \(sourceText). Nåværende verdi er \(serverURL.absoluteString)."
    }

    func isAllowed(url: URL) -> Bool {
        let lowerScheme = url.scheme?.lowercased()
        if ["about", "blob", "data", "file"].contains(lowerScheme) {
            return true
        }
        guard let host = url.host?.lowercased() else {
            return false
        }
        let hosts = Set(allowedHosts + [serverURL.host?.lowercased()].compactMap { $0 })
        return hosts.contains(where: { host == $0 || host.hasSuffix(".\($0)") })
    }
}

private extension AppConfig {
    static func loadBundledConfig() -> [String: Any] {
        guard let url = Bundle.main.url(forResource: "AppConfig", withExtension: "plist"),
              let data = try? Data(contentsOf: url),
              let raw = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
              let dict = raw as? [String: Any]
        else {
            return [:]
        }
        return dict
    }

    static func stringValue(for key: String, in dict: [String: Any]) -> String? {
        guard let value = dict[key] else { return nil }
        if let string = value as? String {
            let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        if let number = value as? NSNumber {
            return number.stringValue
        }
        return nil
    }

    static func boolValue(for key: String, in dict: [String: Any]) -> Bool? {
        guard let value = dict[key] else { return nil }
        if let bool = value as? Bool {
            return bool
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        if let string = value as? String {
            let lowered = string.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["1", "true", "yes", "ja", "on"].contains(lowered) {
                return true
            }
            if ["0", "false", "no", "nei", "off"].contains(lowered) {
                return false
            }
        }
        return nil
    }

    static func numberValue(for key: String, in dict: [String: Any]) -> Double? {
        guard let value = dict[key] else { return nil }
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let string = value as? String {
            return Double(string.replacingOccurrences(of: ",", with: "."))
        }
        return nil
    }

    static func stringArrayValue(for key: String, in dict: [String: Any]) -> [String] {
        guard let value = dict[key] else { return [] }
        if let strings = value as? [String] {
            return strings.map { $0.lowercased().trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        }
        if let string = value as? String {
            return string
                .split(separator: ",")
                .map { String($0).lowercased().trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        }
        if let array = value as? [Any] {
            return array.compactMap {
                if let string = $0 as? String {
                    let trimmed = string.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
                    return trimmed.isEmpty ? nil : trimmed
                }
                return nil
            }
        }
        return []
    }
}
