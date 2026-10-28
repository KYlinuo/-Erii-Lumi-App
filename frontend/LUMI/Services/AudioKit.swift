import AVFoundation
import Foundation

/// 录音器：录制 m4a（AAC 44.1kHz 单声道），停止后返回文件与时长。
///
/// 约束：
/// - 只在用户按下麦克风时申请权限，不在启动时打扰；
/// - 录音文件写在临时目录，发送成功与否都不长期占用空间；
/// - 开关录音都会正确激活/归还 `AVAudioSession`，避免把别的 App 的音量搞乱。
@MainActor
final class AudioRecorder: NSObject, ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var elapsed: TimeInterval = 0
    @Published private(set) var level: Double = 0

    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private var startedAt: Date?
    private var currentURL: URL?

    /// 录音上限：超过自动停止，防止误触录满磁盘。
    private let maxDuration: TimeInterval = 120

    var isAvailable: Bool { true }

    static func requestPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    func start() async throws {
        guard !isRecording else { return }
        let granted = await Self.requestPermission()
        guard granted else { throw RecorderError.permissionDenied }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker])
        try session.setActive(true)

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("lumi-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
        ]
        let recorder = try AVAudioRecorder(url: url, settings: settings)
        recorder.isMeteringEnabled = true
        recorder.delegate = self
        guard recorder.record() else { throw RecorderError.cannotStart }

        self.recorder = recorder
        self.currentURL = url
        self.startedAt = Date()
        self.isRecording = true
        self.elapsed = 0
        startTimer()
    }

    @discardableResult
    func stop() -> (url: URL, duration: TimeInterval)? {
        guard let recorder, let url = currentURL else { return nil }
        recorder.stop()
        stopTimer()
        let duration = recorder.currentTime > 0
            ? recorder.currentTime
            : Date().timeIntervalSince(startedAt ?? Date())
        self.recorder = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)

        guard duration >= 0.3 else {
            try? FileManager.default.removeItem(at: url)
            return nil
        }
        return (url, duration)
    }

    func cancel() {
        guard let recorder, let url = currentURL else { return }
        recorder.stop()
        stopTimer()
        try? FileManager.default.removeItem(at: url)
        self.recorder = nil
        currentURL = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func startTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let recorder = self.recorder else { return }
                self.elapsed = recorder.currentTime
                recorder.updateMeters()
                let power = Double(recorder.averagePower(forChannel: 0))
                // -60dB..0dB 映射到 0..1，用于波形动画
                self.level = max(0, min(1, (power + 60) / 60))
                if self.elapsed >= self.maxDuration {
                    _ = self.stop()
                }
            }
        }
    }

    private func stopTimer() {
        timer?.invalidate()
        timer = nil
        level = 0
    }
}

enum RecorderError: LocalizedError {
    case permissionDenied
    case cannotStart

    var errorDescription: String? {
        switch self {
        case .permissionDenied:
            return "没有麦克风权限。请到 设置 → LUMI → 麦克风 打开后再试。"
        case .cannotStart:
            return "录音启动失败，可能被其它 App 占用。"
        }
    }
}

/// 播放器：同一时刻只播一条语音，点击第二条会自动停掉第一条。
@MainActor
final class AudioPlayer: NSObject, ObservableObject {
    @Published private(set) var playingID: UUID?
    @Published private(set) var progress: Double = 0

    private var player: AVAudioPlayer?
    private var timer: Timer?

    func play(id: UUID, data: Data) {
        if playingID == id {
            stop()
            return
        }
        stop()
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio)
            try session.setActive(true)
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()
            player.play()
            self.player = player
            self.playingID = id
            timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, let player = self.player, player.duration > 0 else { return }
                    self.progress = player.currentTime / player.duration
                }
            }
        } catch {
            self.player = nil
            self.playingID = nil
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        player?.stop()
        player = nil
        playingID = nil
        progress = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}

extension AudioPlayer: AVAudioPlayerDelegate {}
extension AudioRecorder: AVAudioRecorderDelegate {}
