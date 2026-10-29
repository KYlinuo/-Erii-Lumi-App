import SwiftUI

/// 根视图：启动页 → 主界面（Tab：聊天 / 人物 / 记忆 / 日记 / 设置）。
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
struct MainTabs: View {
    @EnvironmentObject private var session: AppSession

    var body: some View {
        TabView {
            ChatView()
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("聊天", systemImage: "bubble.left.and.bubble.right.fill")
                }

            ProfileView(viewModel: session.personaViewModel)
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("人物", systemImage: "person.crop.circle.fill")
                }

            MemoryView(viewModel: session.memoryViewModel)
                .tabItem {
                    Label("记忆", systemImage: "brain")
                }

            DiaryView(viewModel: session.diaryViewModel)
                .tabItem {
                    Label("日记", systemImage: "book.closed.fill")
                }

            SettingsView()
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("设置", systemImage: "gearshape.fill")
                }
        }
        .tint(LUMIStyle.violet)
        // Tab 栏用系统材质而不是默认不透明灰块；
        // 用 iOS 26 SDK 构建时这里会自动变成 Liquid Glass。
        .toolbarBackground(.ultraThinMaterial, for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
        .onAppear {
            // 统一 Tab 栏的玻璃质感
            let appearance = UITabBarAppearance()
            appearance.configureWithTransparentBackground()
            appearance.backgroundEffect = UIBlurEffect(style: .systemThinMaterialDark)
            UITabBar.appearance().standardAppearance = appearance
            UITabBar.appearance().scrollEdgeAppearance = appearance
        }
    }
}
