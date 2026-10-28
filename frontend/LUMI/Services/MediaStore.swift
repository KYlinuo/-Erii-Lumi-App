import Foundation
import SwiftUI
import UIKit

/// 媒体下载缓存：图片气泡与语音播放共用。
///
/// 为什么要单例：`MessageBubble` 会被 SwiftUI 反复重建，
/// 如果每个气泡各自持有网络请求，滚动时会疯狂重复下载。
/// 这里按 `media_id` 做内存缓存 + 并发去重（同一张图只发一次请求）。
@MainActor
final class MediaStore: ObservableObject {
    static let shared = MediaStore()

    @Published private(set) var images: [String: Data] = [:]
    @Published private(set) var audios: [String: Data] = [:]
    @Published private(set) var failures: Set<String> = []

    private var inFlight: Set<String> = []
    private lazy var client = LUMIAPIClient(configuration: { ConfigurationStore.load() })

    func imageData(for id: String) -> Data? { images[id] }
    func audioData(for id: String) -> Data? { audios[id] }
    func hasFailed(_ id: String) -> Bool { failures.contains(id) }

    func loadImage(_ id: String) async {
        guard images[id] == nil, !inFlight.contains(id) else { return }
        inFlight.insert(id)
        defer { inFlight.remove(id) }
        do {
            let data = try await client.downloadMedia(mediaID: id)
            if let image = UIImage(data: data), let compressed = image.jpegData(compressionQuality: 0.82) {
                images[id] = compressed
            } else {
                images[id] = data
            }
            failures.remove(id)
        } catch {
            failures.insert(id)
        }
    }

    func loadAudio(_ id: String) async -> Data? {
        if let cached = audios[id] { return cached }
        if inFlight.contains(id) { return nil }
        inFlight.insert(id)
        defer { inFlight.remove(id) }
        do {
            let data = try await client.downloadMedia(mediaID: id)
            audios[id] = data
            failures.remove(id)
            return data
        } catch {
            failures.insert(id)
            return nil
        }
    }
}
