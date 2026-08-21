import SwiftUI
import WebMediaDLCore

/// visionOS share-sheet adapter. Heavy work waits for Mac pairing confirmation.
public struct WebMediaDLVisionShareView: View {
    public var intake: WebMediaDLShareIntake

    public init(intake: WebMediaDLShareIntake) {
        self.intake = intake
    }

    public var body: some View {
        Form {
            Text("WebMedia DL")
                .accessibilityAddTraits(.isHeader)
            Text(intake.locator)
                .accessibilityLabel("Shared locator")
            Button("Send to paired Mac") {
                Task {
                    let files = intake.filesDestination
                    _ = try? await WebMediaDLWorkerCredentials.loadClient().submit(
                        locator: intake.locator,
                        surface: .visionos,
                        intakeKind: "share_sheet",
                        destinationKind: files == nil ? nil : "files_app",
                        destinationPath: files?.approvedRoot,
                        approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                        bookmarkData: files?.bookmark.bookmarkData ?? WebMediaDLWorkerCredentials.loadBookmark()
                    )
                }
            }
            .accessibilityLabel("Send to paired Mac")
        }
    }
}
