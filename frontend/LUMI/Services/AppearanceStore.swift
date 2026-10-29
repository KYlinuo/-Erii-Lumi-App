import SwiftUI
import UIKit

/// 外观设置：气泡主题、聊天背景、双方头像，全部本地保存。
///
/// 为什么用单例 + ObservableObject：改设置后聊天页必须立刻重绘，
/// 但这条链路不该经过网络或后端，纯本地状态。
@MainActor
final class AppearanceStore: ObservableObject {
    static let shared = AppearanceStore()

    // MARK: - 气泡主题

    @Published var theme: BubbleTheme {
        didSet { defaults.set(theme.rawValue, forKey: Keys.theme) }
    }

    // MARK: - 聊天背景

    @Published private(set) var backgroundImage: UIImage?
    /// 模糊半径 0...24
    @Published var backgroundBlur: Double {
        didSet { defaults.set(backgroundBlur, forKey: Keys.blur) }
    }
    /// 亮度 -0.4...0.4
    @Published var backgroundBrightness: Double {
        didSet { defaults.set(backgroundBrightness, forKey: Keys.brightness) }
    }
    /// 深色遮罩 0...0.75
    @Published var backgroundDim: Double {
        didSet { defaults.set(backgroundDim, forKey: Keys.dim) }
    }

    // MARK: - 头像

    @Published private(set) var myAvatar: UIImage?
    @Published private(set) var characterAvatar: UIImage?

    // MARK: - App 图标

    /// 当前选中的图标（写回时触发系统图标切换）。
    @Published var iconChoice: AppIconChoice {
        didSet {
            defaults.set(iconChoice.rawValue, forKey: Keys.icon)
            Task { @MainActor in
                await Self.applyIcon(iconChoice)
            }
        }
    }

    private let defaults = UserDefaults.standard

    private enum Keys {
        static let theme = "lumi.appearance.theme"
        static let blur = "lumi.appearance.blur"
        static let brightness = "lumi.appearance.brightness"
        static let dim = "lumi.appearance.dim"
        static let icon = "lumi.appearance.icon"
    }

    private enum Files {
        static let background = "chat-background.jpg"
        static let myAvatar = "my-avatar.jpg"
        static let characterAvatar = "character-avatar.jpg"
    }

    private init() {
        let stored = defaults.string(forKey: Keys.theme) ?? BubbleTheme.sakura.rawValue
        theme = BubbleTheme(rawValue: stored) ?? .sakura
        backgroundBlur = defaults.object(forKey: Keys.blur) as? Double ?? 8
        backgroundBrightness = defaults.object(forKey: Keys.brightness) as? Double ?? 0
        backgroundDim = defaults.object(forKey: Keys.dim) as? Double ?? 0.28
        let storedIcon = defaults.string(forKey: Keys.icon) ?? AppIconChoice.default.rawValue
        iconChoice = AppIconChoice(rawValue: storedIcon) ?? .default
        reloadImages()
    }

    /// 把用户选择应用到系统图标（系统弹窗确认后生效）。
    @MainActor
    private static func applyIcon(_ choice: AppIconChoice) async {
        guard UIApplication.shared.supportsAlternateIcons else { return }
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            UIApplication.shared.setAlternateIconName(choice.assetName) { _ in
                continuation.resume()
            }
        }
    }

    // MARK: - 目录

    static func directory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("LUMI/appearance", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func url(_ name: String) -> URL {
        Self.directory().appendingPathComponent(name)
    }

    // MARK: - 读写

    func reloadImages() {
        backgroundImage = Self.loadImage(at: url(Files.background))
        myAvatar = Self.loadImage(at: url(Files.myAvatar))
        characterAvatar = Self.loadImage(at: url(Files.characterAvatar))
    }

    /// 由 PhotosPicker 的原始 Data 写入磁盘（统一压成 JPEG，避免 HEIC 解码开销）
    func saveBackground(_ data: Data) {
        save(data, to: Files.background)
        backgroundImage = Self.loadImage(at: url(Files.background))
    }

    func saveMyAvatar(_ data: Data) {
        save(data, to: Files.myAvatar)
        myAvatar = Self.loadImage(at: url(Files.myAvatar))
    }

    func saveCharacterAvatar(_ data: Data) {
        save(data, to: Files.characterAvatar)
        characterAvatar = Self.loadImage(at: url(Files.characterAvatar))
    }

    func clearBackground() {
        try? FileManager.default.removeItem(at: url(Files.background))
        backgroundImage = nil
    }

    func clearMyAvatar() {
        try? FileManager.default.removeItem(at: url(Files.myAvatar))
        myAvatar = nil
    }

    func clearCharacterAvatar() {
        try? FileManager.default.removeItem(at: url(Files.characterAvatar))
        characterAvatar = nil
    }

    func resetBackgroundAdjustments() {
        backgroundBlur = 8
        backgroundBrightness = 0
        backgroundDim = 0.28
    }

    // MARK: - 私有

    private func save(_ data: Data, to name: String) {
        guard let image = UIImage(data: data) else { return }
        // 背景太大的图会拖慢滚动，限制到 1600 长边
        let resized = Self.downscaled(image, maxEdge: 1600)
        guard let jpeg = resized.jpegData(compressionQuality: 0.85) else { return }
        try? jpeg.write(to: url(name), options: .atomic)
    }

    private static func loadImage(at url: URL) -> UIImage? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }

    private static func downscaled(_ image: UIImage, maxEdge: CGFloat) -> UIImage {
        let longest = max(image.size.width, image.size.height)
        guard longest > maxEdge else { return image }
        let scale = maxEdge / longest
        let target = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: target)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
    }
}

/// 聊天背景：图片（可模糊/调亮/加暗）+ 主题渐变兜底。
struct ChatBackgroundView: View {
    @ObservedObject var appearance: AppearanceStore

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                if let image = appearance.backgroundImage {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: proxy.size.width, height: proxy.size.height)
                        .clipped()
                        .blur(radius: appearance.backgroundBlur)
                        .brightness(appearance.backgroundBrightness)
                } else {
                    LinearGradient(
                        colors: defaultGradient,
                        startPoint: .top,
                        endPoint: .bottom
                    )
                }

                // 统一压暗，保证文字对比度（冰晶主题也需要）
                Color.black.opacity(appearance.backgroundDim)
            }
            .ignoresSafeArea()
        }
    }

    private var defaultGradient: [Color] {
        switch appearance.theme {
        case .sakura:
            return [Color(red: 0.13, green: 0.11, blue: 0.20),
                    Color(red: 0.20, green: 0.15, blue: 0.26)]
        case .midnight:
            return [Color(red: 0.05, green: 0.06, blue: 0.13),
                    Color(red: 0.10, green: 0.09, blue: 0.22)]
        case .crystal:
            return [Color(red: 0.09, green: 0.11, blue: 0.18),
                    Color(red: 0.14, green: 0.16, blue: 0.26)]
        }
    }
}
