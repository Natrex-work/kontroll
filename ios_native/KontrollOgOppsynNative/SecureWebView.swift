import CryptoKit
import SwiftUI
import UIKit
import WebKit

struct DownloadShareItem: Identifiable {
    let id = UUID()
    let url: URL
}

@MainActor
final class WebViewStore: NSObject, ObservableObject {
    @Published var isLoading = false
    @Published var estimatedProgress = 0.0
    @Published var errorMessage: String?
    @Published var downloadItem: DownloadShareItem?

    let webView: WKWebView
    private let config: AppConfig
    private var observations: [NSKeyValueObservation] = []
    private var hasLoadedHome = false
    private var currentDownloadDestination: URL?

    init(config: AppConfig = .shared) {
        self.config = config
        let webConfiguration = WKWebViewConfiguration()
        webConfiguration.defaultWebpagePreferences.allowsContentJavaScript = true
        webConfiguration.allowsInlineMediaPlayback = true
        webConfiguration.mediaTypesRequiringUserActionForPlayback = []
        webConfiguration.websiteDataStore = .default()

        let webView = WKWebView(frame: .zero, configuration: webConfiguration)
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsLinkPreview = false
        webView.scrollView.keyboardDismissMode = .interactive
        if #available(iOS 16.4, *) {
            webView.isInspectable = false
        }

        self.webView = webView
        super.init()

        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.customUserAgent = "FiskerikontrollNative/1.4 iOS"

        let refreshControl = UIRefreshControl()
        refreshControl.addTarget(self, action: #selector(reloadFromPull), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        observations = [
            webView.observe(\.estimatedProgress, options: [.new]) { [weak self] _, change in
                DispatchQueue.main.async {
                    self?.estimatedProgress = change.newValue ?? 0
                }
            }
        ]
    }

    @objc private func reloadFromPull() {
        if webView.url == nil {
            loadHome(force: true)
        } else {
            webView.reload()
        }
    }

    func loadHomeIfNeeded() {
        guard !hasLoadedHome else { return }
        loadHome(force: true)
    }

    func loadHome(force: Bool = false) {
        guard force || !hasLoadedHome else { return }
        hasLoadedHome = true
        var request = URLRequest(url: config.serverURL)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = 60
        webView.load(request)
    }

    private func finishRefreshing() {
        webView.scrollView.refreshControl?.endRefreshing()
    }

    private func sanitizedFileName(_ filename: String) -> String {
        let invalid = CharacterSet(charactersIn: "/:\\?%*|\"<>")
        let parts = filename.components(separatedBy: invalid)
        let clean = parts.joined(separator: "-").trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.isEmpty ? "nedlasting" : clean
    }

    private func shouldTreatAsDownload(_ response: URLResponse) -> Bool {
        if let httpResponse = response as? HTTPURLResponse,
           let disposition = httpResponse.value(forHTTPHeaderField: "Content-Disposition")?.lowercased(),
           disposition.contains("attachment") {
            return true
        }
        let mimeType = response.mimeType?.lowercased() ?? ""
        return mimeType == "application/zip" || mimeType == "application/octet-stream"
    }

    private func normalizedPins() -> Set<String> {
        Set(
            config.pinnedCertificateSHA256
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                .filter { !$0.isEmpty }
        )
    }

    private func digestHex(for data: Data) -> String {
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private func digestBase64(for data: Data) -> String {
        Data(SHA256.hash(data: data)).base64EncodedString().lowercased()
    }
}

extension WebViewStore: WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        isLoading = true
        errorMessage = nil
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isLoading = false
        errorMessage = nil
        finishRefreshing()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        isLoading = false
        finishRefreshing()
        if (error as NSError).code != NSURLErrorCancelled {
            errorMessage = "Kunne ikke laste siden. Kontroller nettverk og serveradresse, og prøv igjen."
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        isLoading = false
        finishRefreshing()
        if (error as NSError).code != NSURLErrorCancelled {
            errorMessage = "Kunne ikke opprette forbindelse til \(AppConfig.shared.displayName). Kontroller nettverk og serveradresse."
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        let scheme = url.scheme?.lowercased() ?? ""
        if ["about", "blob", "data", "file"].contains(scheme) {
            decisionHandler(.allow)
            return
        }
        if ["tel", "mailto"].contains(scheme) {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        if config.isAllowed(url: url) {
            decisionHandler(.allow)
            return
        }
        UIApplication.shared.open(url)
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        let pins = normalizedPins()
        guard !pins.isEmpty else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        var trustError: CFError?
        guard SecTrustEvaluateWithError(trust, &trustError) else {
            errorMessage = "Serverens sertifikat kunne ikke verifiseres. Kontroller appkonfigurasjon og sertifikat."
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        guard let certificate = SecTrustGetCertificateAtIndex(trust, 0) else {
            errorMessage = "Mangler serversertifikat under oppkobling."
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        let certificateData = SecCertificateCopyData(certificate) as Data
        let hexDigest = digestHex(for: certificateData)
        let base64Digest = digestBase64(for: certificateData)
        guard pins.contains(hexDigest) || pins.contains(base64Digest) else {
            errorMessage = "Serverens sertifikat samsvarer ikke med forventet sikkerhetsprofil. Tilkoblingen ble stoppet."
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        completionHandler(.useCredential, URLCredential(trust: trust))
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, decidePolicyFor decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if shouldTreatAsDownload(navigationResponse.response) {
            decisionHandler(.download)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let downloadsFolder = FileManager.default.temporaryDirectory.appendingPathComponent("FiskerikontrollDownloads", isDirectory: true)
        try? FileManager.default.createDirectory(at: downloadsFolder, withIntermediateDirectories: true)
        let destination = downloadsFolder.appendingPathComponent(sanitizedFileName(suggestedFilename))
        currentDownloadDestination = destination
        completionHandler(destination)
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let currentDownloadDestination {
            downloadItem = DownloadShareItem(url: currentDownloadDestination)
        }
        currentDownloadDestination = nil
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        currentDownloadDestination = nil
        errorMessage = "Nedlasting mislyktes. Prøv igjen fra saken."
    }
}

struct SecureWebView: UIViewRepresentable {
    @ObservedObject var store: WebViewStore

    func makeUIView(context: Context) -> WKWebView {
        store.webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
