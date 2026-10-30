import Foundation

/// 本地消息持久化（JSON 文件，原子写入）。
///
/// 目的：App 退出再打开时立刻恢复历史，不依赖网络。
/// 用 actor 保证 Swift 6 严格并发下不会产生数据竞争。
actor MessageStore {
    private let fileURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(directory: URL, filename: String = "messages.json") {
        self.fileURL = directory.appendingPathComponent(filename, isDirectory: false)
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    /// 默认目录：Application Support/LUMI
    nonisolated static func defaultDirectory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("LUMI", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    func load() throws -> [ChatMessage] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        let data = try Data(contentsOf: fileURL, options: .mappedIfSafe)
        do {
            return try decoder.decode([ChatMessage].self, from: data)
        } catch {
            // 文件损坏时不让 App 崩，直接丢弃并备份
            try? data.write(to: fileURL.deletingLastPathComponent()
                .appendingPathComponent("messages.corrupted.json"))
            return []
        }
    }

    func save(_ messages: [ChatMessage]) throws {
        // 目录必须在这里保证存在：init 只拿到 URL，可能来自测试或自定义路径，
        // 依赖 defaultDirectory() 先建目录会在别处直接 NSCocoaError Code=4。
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try encoder.encode(messages)
        try data.write(to: fileURL, options: .atomic)
    }

    func clear() throws {
        if FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }
    }

    nonisolated var locationDescription: String { fileURL.path }
}
