import Foundation
import LiveKit

/// 一次实时语音通话的 LiveKit 会话。
///
/// 职责：连接房间、发布麦克风、订阅远端（绘梨衣 Agent 的）音频。
/// 视频模式不通过摄像头——绘梨衣的「影像」是本地渲染的角色立绘动画，
/// 用户可关闭摄像头输入，只观看角色影像并与之对话（符合产品设定）。
///
/// 麦克风用 LiveKit 2.x 的 `setMicrophone(enabled:)`：
/// 它内部会创建并发布本地音轨、处理回声消除/降噪，比手动 publish 更稳。
@MainActor
final class LiveCallSession: ObservableObject {
    @Published private(set) var isConnected = false
    @Published private(set) var isConnecting = false
    @Published private(set) var errorMessage: String?

    private var room: Room?

    /// 连接 LiveKit 房间并开启麦克风。
    func connect(url: String, token: String) async {
        isConnecting = true
        errorMessage = nil
        defer { isConnecting = false }

        let newRoom = Room()
        do {
            try await newRoom.connect(url: url, token: token)
            try await newRoom.localParticipant.setMicrophone(enabled: true)
            room = newRoom
            isConnected = true
        } catch {
            errorMessage = error.localizedDescription
            isConnected = false
        }
    }

    /// 挂断：断开房间、释放音轨。
    func disconnect() {
        Task { @MainActor in
            await room?.disconnect()
            room = nil
            isConnected = false
        }
    }

    /// 静音/取消静音（本地麦克风）。
    func setMuted(_ muted: Bool) {
        Task { @MainActor in
            try? await room?.localParticipant.setMicrophone(enabled: !muted)
        }
    }
}
