import SwiftUI
import UIKit

/// Image decoding and failures are local to this row, never a whole-list publication.
struct MessageImageView: View {
    let mediaID: String?
    let localPath: String?
    var onPreview: ((UIImage) -> Void)?
    @State private var image: UIImage?
    @State private var failed = false
    @State private var retry = 0

    private var resourceKey: String { "\(mediaID ?? "")|\(localPath ?? "")|\(retry)" }

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .onTapGesture { onPreview?(image) }
            } else {
                VStack(spacing: 8) {
                    if failed {
                        Image(systemName: "exclamationmark.triangle")
                        Button("重新加载") { retry += 1 }
                    } else { ProgressView("加载图片…").tint(.white) }
                }
                .frame(width: 168, height: 168)
                .background(Color.white.opacity(0.08))
            }
        }
        .task(id: resourceKey) {
            failed = false
            image = nil
            do {
                let decoded = try await MediaStore.shared.image(id: mediaID, localPath: localPath)
                try Task.checkCancellation()
                image = UIImage(cgImage: decoded.cgImage)
            } catch is CancellationError { } catch {
                if !Task.isCancelled { failed = true }
            }
        }
    }
}
