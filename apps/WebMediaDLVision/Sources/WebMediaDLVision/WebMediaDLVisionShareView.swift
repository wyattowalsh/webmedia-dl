import SwiftUI
import WebMediaDLCore

/// visionOS share-sheet adapter. Heavy work waits for Mac pairing confirmation.
public struct WebMediaDLVisionShareView: View {
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
                    do {
                        status = try await WebMediaDLPairedMacSubmit.submit(
                            locator: intake.locator,
                            surface: .visionos,
                            credentials: WebMediaDLWorkerCredentials.loadClient(),
                            intakeKind: "share_sheet",
                            destinationKind: files == nil ? nil : "staging_only"
                        )
                    } catch {
                        status = error.localizedDescription
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
