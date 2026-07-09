import Foundation
import Network

final class BonjourBroadcaster: ObservableObject {
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "sentinel.bonjour")
    @Published var isBroadcasting = false

    func start(serviceName: String = "SentinelDesk") {
        stop()
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true

        guard let listener = try? NWListener(using: params, on: .any) else {
            NSLog("Bonjour: failed to create listener")
            return
        }

        let service = NWListener.Service(name: serviceName, type: "_sentinel._tcp")
        listener.service = service

        listener.newConnectionHandler = { conn in
            conn.cancel()
        }

        listener.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                self?.isBroadcasting = (state == .ready)
            }
            NSLog("Bonjour: listener \(state)")
        }

        listener.start(queue: queue)
        self.listener = listener
        NSLog("Bonjour: broadcasting as \(serviceName)")
    }

    func stop() {
        listener?.cancel()
        listener = nil
        isBroadcasting = false
    }
}
