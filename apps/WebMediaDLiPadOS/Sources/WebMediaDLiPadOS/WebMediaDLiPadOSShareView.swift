import SwiftUI
import WebMediaDLCore

/// iPad share-sheet adapter. Heavy work waits for Mac pairing confirmation.
public struct WebMediaDLiPadOSShareView: View {
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
                _ = WebMediaDLLoopbackClient().submitRequest(
                    locator: intake.locator,
                    surface: .ipados
                )
            }
            .accessibilityLabel("Send to paired Mac")
        }
    }
}
