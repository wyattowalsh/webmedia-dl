import SwiftUI
import WebMediaDLCore

/// macOS share-sheet adapter. Does not run provider argv.
public struct WebMediaDLMacShareView: View {
    public var intake: WebMediaDLShareIntake
    private let client = WebMediaDLLoopbackClient()

    public init(intake: WebMediaDLShareIntake) {
        self.intake = intake
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Send to WebMedia DL")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Text(intake.locator)
                .accessibilityLabel("Shared locator")
            Button("Send to WebMedia DL") {
                Task {
                    _ = try? await client.submit(locator: intake.locator, surface: .macos)
                }
            }
            .accessibilityLabel("Send to WebMedia DL")
            if intake.canPublishToPhotos {
                Text("Photos destination is user-approved.")
            } else {
                Text("Photos and Files require an approved root.")
                    .accessibilityLabel("Photos destination blocked without approval")
            }
        }
        .padding()
    }
}
