import Foundation
import LocalAuthentication
import SwiftUI

/// 应用锁：Face ID / Touch ID 解锁（可选）。
///
/// - 偏好保存在 UserDefaults（仅本机，不涉及服务器）；
/// - 实际鉴权走系统 `LocalAuthentication`，App 不接触生物特征数据；
/// - 默认关闭，开启后每次从后台回到前台要求验证一次。
@MainActor
final class AppLockStore: ObservableObject {
    static let shared = AppLockStore()

    @Published private(set) var isEnabled: Bool {
        didSet { UserDefaults.standard.set(isEnabled, forKey: Key.enabled) }
    }
    @Published private(set) var isLocked: Bool = false

    private enum Key {
        static let enabled = "erii.applock.enabled"
    }

    private init() {
        isEnabled = UserDefaults.standard.bool(forKey: Key.enabled)
    }

    func setEnabled(_ enabled: Bool) {
        isEnabled = enabled
        if !enabled { isLocked = false }
    }

    /// 生物识别是否可用（Face ID / Touch ID）。
    static func biometricTypeName() -> String? {
        let ctx = LAContext()
        var error: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            return nil
        }
        switch ctx.biometryType {
        case .faceID: return "Face ID"
        case .touchID: return "Touch ID"
        default: return "生物识别"
        }
    }

    /// 上锁（进入后台时调用）。
    func lock() {
        guard isEnabled else { return }
        isLocked = true
    }

    /// 尝试解锁；成功返回 true。
    func unlock() async -> Bool {
        guard isEnabled, isLocked else { return true }
        let ctx = LAContext()
        ctx.localizedFallbackTitle = "使用密码"
        var error: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            // 无法用系统鉴权时直接放行（例如模拟器），避免把用户锁死。
            isLocked = false
            return true
        }
        let ok = await withCheckedContinuation { continuation in
            ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "解锁绘梨衣") { success, _ in
                continuation.resume(returning: success)
            }
        }
        if ok { isLocked = false }
        return ok
    }
}
