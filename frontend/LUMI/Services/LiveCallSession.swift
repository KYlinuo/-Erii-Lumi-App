import Foundation
import LiveKit

/// 一次实时语音通话的 LiveKit 会话。
///
/// 职责：连接房间、发布麦克风、订阅远端（绘梨衣 Agent 的）音频。
/// 视频模式不通过摄像头——绘梨衣的「影像」是本地渲染的角色立绘动画，
/// 用户可关闭摄像头输入，只观看角色影像并与之对话（符合产品设定）。
@MainActor
final class LiveCallSession: ObservableObject {
    @Published private(set) var isConnected = false
    @Published private(set) var isConnecting = false
    @Published private(set) var errorMessage: String?

    private var room: Room?

    /// 连接 LiveKit 房间并发布麦克风。
    func connect(url: String, token: String) async {
        isConnecting = true
        errorMessage = nil
        defer { isConnecting = false }

        let newRoom = Room(delegate: self)
        do {
            try await newRoom.connect(url: url, token: token)
            // 发布麦克风（音频采集）
            if let mic = LocalAudioTrack.createTrack() {
                try await newRoom.localParticipant.publishAudioTrack(track: mic)
            }
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
            guard let mic = room?.localParticipant.firstAudioTrack else { return }
            _ = try? await room?.localParticipant.setTrack(muted: muted, track: mic)
        }
    }
}

extension LiveCallSession: RoomDelegate {
    nonisolated func room(_ room: Room, didUpdateConnectionState connectionState: ConnectionState, from oldValue: ConnectionState) {
        Task { @MainActor in
            switch connectionState {
            case .connected:
                self.isConnected = true
            case .disconnected, .failed:
                self.isConnected = false
                if case .failed = connectionState {
                    self.errorMessage = "通话连接失败。"
                }
            default:
                break
            }
        }
    }
}
