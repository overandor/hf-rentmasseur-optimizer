import Foundation
import Combine

struct AppleTVDevice: Identifiable, Hashable {
    let id: String
    let name: String
    let host: String
    let port: Int
    var isPaired: Bool = false

    init(id: String, name: String, host: String, port: Int = 7000) {
        self.id = id
        self.name = name
        self.host = host
        self.port = port
    }
}

final class AppleTVDiscovery: NSObject, ObservableObject {
    @Published var devices: [AppleTVDevice] = []
    @Published var isScanning: Bool = false

    private var browsers: [NetServiceBrowser] = []
    private var discoveredServices: [NetService] = []
    private let queue = DispatchQueue(label: "com.membra.tvhub.discovery")

    func startDiscovery() {
        guard !isScanning else { return }
        isScanning = true
        devices = []

        let serviceTypes = ["_airplay._tcp", "_raop._tcp", "_touch-able._tcp"]
        for serviceType in serviceTypes {
            let browser = NetServiceBrowser()
            browser.delegate = self
            browser.searchForServices(ofType: serviceType, inDomain: "")
            browsers.append(browser)
        }
    }

    func stopDiscovery() {
        for browser in browsers {
            browser.stop()
        }
        browsers = []
        isScanning = false
    }

    func refresh() {
        stopDiscovery()
        startDiscovery()
    }
}

extension AppleTVDiscovery: NetServiceBrowserDelegate, NetServiceDelegate {
    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        discoveredServices.append(service)
        service.delegate = self
        service.resolve(withTimeout: 5)
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        if let idx = discoveredServices.firstIndex(where: { $0 === service }) {
            discoveredServices.remove(at: idx)
        }
        let host = service.hostName ?? ""
        DispatchQueue.main.async {
            self.devices.removeAll { $0.host == host }
        }
    }

    func netServiceDidResolveAddress(_ sender: NetService) {
        let host = sender.hostName ?? ""
        guard !host.isEmpty else { return }

        let name = sender.name
        let port = sender.port > 0 ? sender.port : 7000
        let deviceId = "\(host):\(port)"

        DispatchQueue.main.async {
            if !self.devices.contains(where: { $0.id == deviceId }) {
                let device = AppleTVDevice(id: deviceId, name: name, host: host, port: port)
                self.devices.append(device)
            }
        }
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        NSLog("TVHub: Failed to resolve service: \(errorDict)")
    }
}
