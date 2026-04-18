import SwiftUI

struct SessionLockView: View {
    let isAuthenticating: Bool
    let errorMessage: String?
    let unlockAction: () -> Void

    var body: some View {
        ZStack {
            Rectangle()
                .fill(.ultraThinMaterial)
                .ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 56))
                    .foregroundStyle(.tint)
                Text("Låst app")
                    .font(.title2.weight(.semibold))
                Text("Appen krever identifisering før kontrollopplysninger vises.")
                    .font(.body)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.red)
                }
                Button(action: unlockAction) {
                    HStack(spacing: 10) {
                        if isAuthenticating {
                            ProgressView()
                                .progressViewStyle(.circular)
                        }
                        Text(isAuthenticating ? "Verifiserer" : "Lås opp")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isAuthenticating)
                .padding(.top, 8)
            }
            .padding(24)
            .frame(maxWidth: 420)
        }
    }
}
