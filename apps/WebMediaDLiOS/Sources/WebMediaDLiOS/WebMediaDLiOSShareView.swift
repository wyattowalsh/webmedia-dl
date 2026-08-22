import SwiftUI
import WebMediaDLCore

/// iOS share-sheet adapter. Heavy work waits for Mac pairing confirmation.
public struct WebMediaDLiOSShareView: View {
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
                    let intake = self.intake.resolvedForSubmit()
                    let files = intake.filesDestination
                    _ = try? await WebMediaDLPairedMacSubmit.submit(
                        locator: intake.locator,
                        surface: .ios,
                        credentials: WebMediaDLWorkerCredentials.loadClient(),
                        intakeKind: "share_sheet",
                        destinationKind: files == nil ? nil : "staging_only"
                    )
                }
            }
            .accessibilityLabel("Send to paired Mac")
        }
    }
}
