import SwiftUI

@main
struct LUMIApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
            // 不在这里强制深色：让设置/人物/记忆/日记等页面跟随系统浅色/深色。
            // 聊天页内部会单独保持深色（壁纸 + 气泡风格）。
        }
    }
}
