import SwiftUI
import WebMediaDLCore

/// macOS share-sheet adapter. Does not run provider argv.
public struct WebMediaDLMacShareView: View {
    public var intake: WebMediaDLShareIntake
    private let client = WebMediaDLWorkerCredentials.loadClient()
    @State private var status = ""

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
                    let intake = self.intake.resolvedForSubmit()
                    let files = intake.filesDestination
                    status = await WebMediaDLLoopbackClient.displayedResponse {
                        try await client.submit(
                            locator: intake.locator,
                            surface: .macos,
                            intakeKind: "share_sheet",
                            destinationKind: files == nil ? nil : "files_app",
                            destinationPath: files?.approvedRoot,
                            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
                        )
                    }
                }
            }
            .accessibilityLabel("Send to WebMedia DL")
            if !status.isEmpty {
                Text(status)
                    .accessibilityLabel("Job status")
            }
            if intake.canPublishToFiles {
                Text("Files destination is user-approved.")
                    .accessibilityLabel("Files destination is user-approved")
            } else {
                Text("Photos and Files require an approved root.")
                    .accessibilityLabel("Photos destination blocked without approval")
            }
            if intake.canPublishToPhotos {
                Text("Photos destination is user-approved.")
            }
        }
        .padding()
    }
}
