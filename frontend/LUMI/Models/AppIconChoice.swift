import SwiftUI

/// App 图标选项（与 Assets.xcassets 里的 .appiconset 一一对应）。
///
/// 注意：iOS 不允许把任意相册图片直接设为系统图标——
/// 系统图标必须**预先打包**在 app bundle 里，通过
/// `UIApplication.setAlternateIconName` 切换（见 AppearanceStore）。
enum AppIconChoice: String, CaseIterable, Identifiable {
    /// 默认（与 CFBundlePrimaryIcon 对应，setAlternateIconName(nil) 恢复）
    case `default`
    case sakura
    case night
    case ice

    var id: String { rawValue }

    /// 对应 .appiconset 目录名；`nil` 表示使用默认图标。
    var assetName: String? {
        switch self {
        case .default: return nil
        case .sakura: return "AppIconSakura"
        case .night: return "AppIconNight"
        case .ice: return "AppIconIce"
        }
    }

    var title: String {
        switch self {
        case .default: return "默认 · 绘梨衣"
        case .sakura: return "樱色微光"
        case .night: return "深夜星河"
        case .ice: return "透明冰晶"
        }
    }

    var subtitle: String {
        switch self {
        case .default: return "原图，温柔的水彩风"
        case .sakura: return "明亮偏粉，适合白天"
        case .night: return "低饱和夜色，护眼"
        case .ice: return "清爽冷白，突出玻璃质感"
        }
    }

    /// 预览用的图片资源名（.appiconset 内 1024px 主图）。
    var previewImageName: String {
        switch self {
        case .default: return "AppIcon-1024"
        case .sakura: return "AppIconSakura-1024"
        case .night: return "AppIconNight-1024"
        case .ice: return "AppIconIce-1024"
        }
    }
}
