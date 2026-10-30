import Foundation
import ImageIO
import CoreGraphics

/// Immutable decoded pixels. CGImage is retained for read-only rendering across actors.
final class DecodedImage: @unchecked Sendable {
    let cgImage: CGImage
    init(_ image: CGImage) { cgImage = image }
    var cost: Int { cgImage.bytesPerRow * cgImage.height }
}

/// No ObservableObject broadcast: each image row awaits only its own resource.
/// Decode on this actor, cache by resource/size/server, and share concurrent requests.
///
/// 分层缓存（跨尺寸复用下载）：
/// - `rawData` 按「资源」（本地路径，或 服务器 + 媒体 ID，不含尺寸）缓存下载到的
///   原始字节，让列表 960px 与全屏 2560px 共用同一次网络下载；
/// - `images` 按「资源 + 目标尺寸」缓存解码结果，避免重复解码；
/// - 同一资源的并发请求（含不同尺寸）共享同一个下载任务，不会重复拉取。
actor MediaStore {
    static let shared = MediaStore()
    typealias Download = @Sendable (String) async throws -> Data
    private let injectedDownload: Download?
    private let images = NSCache<NSString, DecodedImage>()
    private let rawData = NSCache<NSString, NSData>()
    private let audios = NSCache<NSString, NSData>()
    private var imageTasks: [String: Task<DecodedImage, Error>] = [:]
    private var dataTasks: [String: Task<Data, Error>] = [:]
    private var audioTasks: [String: Task<Data, Error>] = [:]

    init(download: Download? = nil) {
        injectedDownload = download
        images.totalCostLimit = 48 * 1_024 * 1_024
        images.countLimit = 80
        // 原始字节只为了近期跨尺寸复用，成本上限设小，避免常驻整张原图。
        rawData.totalCostLimit = 16 * 1_024 * 1_024
        rawData.countLimit = 40
        audios.totalCostLimit = 12 * 1_024 * 1_024
        audios.countLimit = 20
    }

    func image(id: String?, localPath: String?, maxPixelSize: Int = 960) async throws -> DecodedImage {
        let configuration = ConfigurationStore.load()
        let size = max(1, min(maxPixelSize, 2_560))
        let resource = localPath ?? "\(configuration.baseURL.absoluteString)|\(id ?? "")"
        let key = "\(resource)|\(size)"
        if let cached = images.object(forKey: key as NSString) { return cached }
        if let task = imageTasks[key] { return try await task.value }
        let task = Task { () throws -> DecodedImage in
            let data = try await self.rawData(
                resource: resource, id: id, localPath: localPath, configuration: configuration
            )
            return try Self.decode(data, maxPixelSize: size)
        }
        imageTasks[key] = task
        defer { imageTasks[key] = nil }
        let image = try await task.value
        images.setObject(image, forKey: key as NSString, cost: image.cost)
        return image
    }

    func loadAudio(_ id: String) async -> Data? {
        let configuration = ConfigurationStore.load()
        let key = "\(configuration.baseURL.absoluteString)|\(id)"
        if let cached = audios.object(forKey: key as NSString) { return cached as Data }
        if let task = audioTasks[key] { return try? await task.value }
        let task = Task { try await self.download(id, configuration: configuration) }
        audioTasks[key] = task
        defer { audioTasks[key] = nil }
        guard let data = try? await task.value else { return nil }
        if data.count <= 12 * 1_024 * 1_024 {
            audios.setObject(data as NSData, forKey: key as NSString, cost: data.count)
        }
        return data
    }

    func clearCache() {
        images.removeAllObjects()
        rawData.removeAllObjects()
        audios.removeAllObjects()
    }

    /// 取原始字节：按资源合并并发请求，短时缓存以便跨尺寸复用。
    private func rawData(
        resource: String,
        id: String?,
        localPath: String?,
        configuration: ServerConfiguration
    ) async throws -> Data {
        if let cached = rawData.object(forKey: resource as NSString) { return cached as Data }
        if let task = dataTasks[resource] { return try await task.value }
        let task = Task { () throws -> Data in
            if let localPath, FileManager.default.fileExists(atPath: localPath) {
                return try Data(contentsOf: URL(fileURLWithPath: localPath), options: .mappedIfSafe)
            } else if let id, !id.isEmpty {
                return try await self.download(id, configuration: configuration)
            } else {
                throw LUMIError.upstreamBadResponse
            }
        }
        dataTasks[resource] = task
        defer { dataTasks[resource] = nil }
        let data = try await task.value
        if data.count <= 16 * 1_024 * 1_024 {
            rawData.setObject(data as NSData, forKey: resource as NSString, cost: data.count)
        }
        return data
    }

    private func download(_ id: String, configuration: ServerConfiguration) async throws -> Data {
        if let injectedDownload { return try await injectedDownload(id) }
        let client = LUMIAPIClient(configuration: { configuration })
        return try await client.downloadMedia(mediaID: id)
    }

    static func decode(_ data: Data, maxPixelSize: Int) throws -> DecodedImage {
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
              ] as CFDictionary) else { throw LUMIError.upstreamBadResponse }
        return DecodedImage(image)
    }
}
