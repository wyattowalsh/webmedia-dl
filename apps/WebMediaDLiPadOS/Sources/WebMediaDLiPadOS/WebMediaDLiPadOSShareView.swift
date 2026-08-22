import SwiftUI
import WebMediaDLCore

/// iPad share-sheet adapter. Heavy work waits for Mac pairing confirmation.
public struct WebMediaDLiPadOSShareView: View {
    public var intake: WebMediaDLShareIntake
    @State private var status = ""

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
                    status = await WebMediaDLLoopbackClient.displayedResponse {
                        try await WebMediaDLPairedMacSubmit.submit(
                            locator: intake.locator,
                            surface: .ipados,
                            credentials: WebMediaDLWorkerCredentials.loadClient(),
                            intakeKind: "share_sheet",
                            destinationKind: files == nil ? nil : "staging_only"
                        )
                    }
                }
            }
            .accessibilityLabel("Send to paired Mac")
            if !status.isEmpty {
                Text(status)
                    .accessibilityLabel("Job status")
            }
        }
    }
}
