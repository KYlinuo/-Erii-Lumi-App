import SwiftUI
import UIKit

/// 根视图：启动页 → 主界面（聊天 / 小本子 / 我）。
struct RootView: View {
    @EnvironmentObject private var session: AppSession
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var appLock = AppLockStore.shared

    var body: some View {
        Group {
            switch session.phase {
            case .launching:
                LaunchView(status: session.launchStatus) {
                    session.enterChat()
                }
            case .ready:
                MainTabs()
                    .environmentObject(session)
            }
        }
        .animation(.easeInOut, value: session.phase == .ready)
        .overlay {
            if appLock.isLocked {
                LockScreenView(appLock: appLock)
                    .transition(.opacity)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background {
                appLock.lock()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didReceiveMemoryWarningNotification)) { _ in
            Task { await MediaStore.shared.clearCache() }
        }
        .task {
            await session.bootstrap()
        }
    }
}

/// 应用锁屏：点击后走系统 Face ID / Touch ID 验证。
struct LockScreenView: View {
    @ObservedObject var appLock: AppLockStore

    var body: some View {
        ZStack {
            LUMIStyle.pageBackground.ignoresSafeArea()
            VStack(spacing: 18) {
                Image(systemName: "faceid")
                    .font(.system(size: 56))
                    .foregroundStyle(LUMIStyle.violet)
                Text("绘梨衣")
                    .font(.title2.weight(.medium))
                Text("点击解锁继续")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Button("解锁") {
                    Task { _ = await appLock.unlock() }
                }
                .buttonStyle(.borderedProminent)
                .tint(LUMIStyle.violet)
                .padding(.top, 6)
            }
        }
        .onAppear {
            Task { _ = await appLock.unlock() }
        }
    }
}

/// 主界面：原生 TabView + 统一视觉。
/// 36 项需求 01：主入口收敛为「聊天 / 小本子 / 我」。
struct MainTabs: View {
    @EnvironmentObject private var session: AppSession

    var body: some View {
        TabView {
            NavigationStack {
                ChatView().environmentObject(session.chatViewModel)
            }
                .tabItem {
                    Label("聊天", systemImage: "bubble.left.and.bubble.right.fill")
                }

            NotebookView()
                .environmentObject(session)
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("小本子", systemImage: "book.closed.fill")
                }

            MeView()
                .environmentObject(session)
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("我", systemImage: "person.crop.circle.fill")
                }
        }
        .tint(LUMIStyle.violet)
        // Let the linked system SDK provide native tab-bar materials and accessibility.
    }
}
