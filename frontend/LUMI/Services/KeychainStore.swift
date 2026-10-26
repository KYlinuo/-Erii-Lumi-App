import Foundation
import Security

/// Keychain 访问封装。
///
/// 使用 `kSecClassGenericPassword`，可访问性设为
/// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`——备份不会带走令牌。
final class KeychainStore: Sendable {
    static let shared = KeychainStore()

    enum Key: String, Sendable {
        case accessToken = "com.projectlumi.keychain.accessToken"
    }

    private let service = "com.projectlumi.LUMI"

    private init() {}

    func save(_ value: String, for key: Key) throws {
        guard let data = value.data(using: .utf8) else { throw KeychainError.encodingFailed }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]

        // 先尝试更新，不存在时再新增
        let attributes: [String: Any] = [kSecValueData as String: data]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        switch updateStatus {
        case errSecSuccess:
            return
        case errSecItemNotFound:
            let addStatus = SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil)
            guard addStatus == errSecSuccess else { throw KeychainError.unhandled(addStatus) }
        default:
            throw KeychainError.unhandled(updateStatus)
        }
    }

    func read(_ key: Key) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        switch status {
        case errSecSuccess:
            guard let data = result as? Data else { throw KeychainError.unexpectedData }
            return String(data: data, encoding: .utf8)
        case errSecItemNotFound:
            return nil
        default:
            throw KeychainError.unhandled(status)
        }
    }

    func delete(_ key: Key) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unhandled(status)
        }
    }
}

enum KeychainError: LocalizedError, Sendable, Equatable {
    case encodingFailed
    case unexpectedData
    case unhandled(OSStatus)

    var errorDescription: String? {
        switch self {
        case .encodingFailed:
            return "令牌无法编码为 UTF-8。"
        case .unexpectedData:
            return "Keychain 返回的数据类型异常。"
        case .unhandled(let status):
            return "Keychain 操作失败（OSStatus \(status)）。"
        }
    }
}
