//
//  FinanceEngine.swift
//  CursorAgent OS
//
//  Read-only finance capabilities for the Finance cursor.
//  - Read financial data (JSON/CSV) from workspace
//  - Draft invoices (write to workspace, never send)
//  - Cashflow analysis
//  - Expense review
//  - Risk assessment
//  - NO network, NO payment, NO external API — enforced by permissions
//

import Foundation
import CryptoKit

// MARK: - Finance Data Models

public struct FinancialSnapshot: Codable, Identifiable {
    public let id: String
    public let timestamp: Double
    public let totalRevenue: Double
    public let totalExpenses: Double
    public let netProfit: Double
    public let profitMargin: Double
    public let cashOnHand: Double
    public let outstandingInvoices: Double
    public let overdueInvoices: Double
    public let monthlyBurn: Double
    public let runwayMonths: Int
    public let currency: String

    public init(totalRevenue: Double, totalExpenses: Double, cashOnHand: Double,
                outstandingInvoices: Double, overdueInvoices: Double,
                monthlyBurn: Double, currency: String = "USD") {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.totalRevenue = totalRevenue
        self.totalExpenses = totalExpenses
        self.netProfit = totalRevenue - totalExpenses
        self.profitMargin = totalRevenue > 0 ? (netProfit / totalRevenue) * 100 : 0
        self.cashOnHand = cashOnHand
        self.outstandingInvoices = outstandingInvoices
        self.overdueInvoices = overdueInvoices
        self.monthlyBurn = monthlyBurn
        self.runwayMonths = monthlyBurn > 0 ? Int(cashOnHand / monthlyBurn) : 999
        self.currency = currency
    }
}

public struct Invoice: Codable, Identifiable {
    public let id: String
    public let invoiceNumber: String
    public let clientName: String
    public let clientEmail: String?
    public let issueDate: Double
    public let dueDate: Double
    public let lineItems: [InvoiceLineItem]
    public let subtotal: Double
    public let taxRate: Double
    public let taxAmount: Double
    public let total: Double
    public let currency: String
    public var status: InvoiceStatus
    public let notes: String?

    public enum InvoiceStatus: String, Codable, CaseIterable {
        case draft     = "draft"
        case sent      = "sent"
        case paid      = "paid"
        case overdue   = "overdue"
        case cancelled = "cancelled"
    }

    public init(invoiceNumber: String, clientName: String, clientEmail: String? = nil,
                issueDate: Double = Date().timeIntervalSince1970,
                dueDate: Double = Date().timeIntervalSince1970 + 30 * 86400,
                lineItems: [InvoiceLineItem], taxRate: Double = 0.0,
                currency: String = "USD", notes: String? = nil) {
        self.id = UUID().uuidString.prefix(20).description
        self.invoiceNumber = invoiceNumber
        self.clientName = clientName
        self.clientEmail = clientEmail
        self.issueDate = issueDate
        self.dueDate = dueDate
        self.lineItems = lineItems
        self.subtotal = lineItems.reduce(0) { $0 + $1.total }
        self.taxRate = taxRate
        self.taxAmount = subtotal * (taxRate / 100)
        self.total = subtotal + taxAmount
        self.currency = currency
        self.status = .draft
        self.notes = notes
    }
}

public struct InvoiceLineItem: Codable, Identifiable {
    public let id: String
    public let description: String
    public let quantity: Double
    public let unitPrice: Double
    public let total: Double

    public init(description: String, quantity: Double, unitPrice: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.description = description
        self.quantity = quantity
        self.unitPrice = unitPrice
        self.total = quantity * unitPrice
    }
}

public struct ExpenseRecord: Codable, Identifiable {
    public let id: String
    public let date: Double
    public let category: ExpenseCategory
    public let description: String
    public let amount: Double
    public let currency: String
    public let vendor: String?
    public let recurring: Bool

    public enum ExpenseCategory: String, Codable, CaseIterable {
        case payroll       = "payroll"
        case infrastructure = "infrastructure"
        case software      = "software"
        case marketing     = "marketing"
        case travel        = "travel"
        case office        = "office"
        case legal         = "legal"
        case other         = "other"

        public var glyph: String {
            switch self {
            case .payroll:        return "👥"
            case .infrastructure: return "🖥"
            case .software:       return "💾"
            case .marketing:      return "📢"
            case .travel:         return "✈"
            case .office:         return "🏢"
            case .legal:          return "⚖"
            case .other:          return "📦"
            }
        }
    }

    public init(date: Double, category: ExpenseCategory, description: String,
                amount: Double, currency: String = "USD", vendor: String? = nil,
                recurring: Bool = false) {
        self.id = UUID().uuidString.prefix(16).description
        self.date = date
        self.category = category
        self.description = description
        self.amount = amount
        self.currency = currency
        self.vendor = vendor
        self.recurring = recurring
    }
}

public struct CashflowEntry: Codable, Identifiable {
    public let id: String
    public let date: Double
    public let amount: Double
    public let direction: CashflowDirection
    public let category: String
    public let description: String

    public enum CashflowDirection: String, Codable {
        case inflow  = "inflow"
        case outflow = "outflow"

        public var glyph: String { self == .inflow ? "▲" : "▼" }
        public var sign: Double { self == .inflow ? 1 : -1 }
    }

    public init(date: Double, amount: Double, direction: CashflowDirection,
                category: String, description: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.date = date
        self.amount = amount
        self.direction = direction
        self.category = category
        self.description = description
    }
}

// MARK: - Finance Risk Assessment

public struct FinanceRiskAssessment: Codable, Identifiable {
    public let id: String
    public let timestamp: Double
    public let overallRisk: FinanceRiskLevel
    public let cashRisk: FinanceRiskLevel
    public let revenueRisk: FinanceRiskLevel
    public let expenseRisk: FinanceRiskLevel
    public let invoiceRisk: FinanceRiskLevel
    public let findings: [FinanceRiskFinding]
    public let recommendations: [String]

    public enum FinanceRiskLevel: String, Codable, CaseIterable {
        case low      = "low"
        case moderate = "moderate"
        case elevated = "elevated"
        case high     = "high"
        case severe   = "severe"

        public var glyph: String {
            switch self {
            case .low:      return "◇"
            case .moderate: return "○"
            case .elevated: return "▲"
            case .high:     return "⟁"
            case .severe:   return "⛔"
            }
        }
    }

    public init(overallRisk: FinanceRiskLevel, cashRisk: FinanceRiskLevel,
                revenueRisk: FinanceRiskLevel, expenseRisk: FinanceRiskLevel,
                invoiceRisk: FinanceRiskLevel, findings: [FinanceRiskFinding],
                recommendations: [String]) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.overallRisk = overallRisk
        self.cashRisk = cashRisk
        self.revenueRisk = revenueRisk
        self.expenseRisk = expenseRisk
        self.invoiceRisk = invoiceRisk
        self.findings = findings
        self.recommendations = recommendations
    }
}

public struct FinanceRiskFinding: Codable, Identifiable {
    public let id: String
    public let severity: FinanceRiskAssessment.FinanceRiskLevel
    public let category: String
    public let description: String
    public let impact: String

    public init(severity: FinanceRiskAssessment.FinanceRiskLevel, category: String,
                description: String, impact: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.severity = severity
        self.category = category
        self.description = description
        self.impact = impact
    }
}

// MARK: - Finance Engine

public final class FinanceEngine: ObservableObject {
    @Published public var snapshot: FinancialSnapshot?
    @Published public var invoices: [Invoice] = []
    @Published public var expenses: [ExpenseRecord] = []
    @Published public var cashflow: [CashflowEntry] = []
    @Published public var riskAssessment: FinanceRiskAssessment?
    @Published public var lastReadError: String?

    public let workspaceRoot: URL
    public let dataDirectory: URL

    public init(workspaceRoot: URL) {
        self.workspaceRoot = workspaceRoot
        self.dataDirectory = workspaceRoot.appendingPathComponent(".finance_data")
        try? FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        loadData()
    }

    // MARK: - Load Data from Workspace

    public func loadData() {
        loadInvoices()
        loadExpenses()
        loadCashflow()
        computeSnapshot()
    }

    private func loadInvoices() {
        let url = dataDirectory.appendingPathComponent("invoices.json")
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode([Invoice].self, from: data) {
            invoices = decoded
        }
    }

    private func loadExpenses() {
        let url = dataDirectory.appendingPathComponent("expenses.json")
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode([ExpenseRecord].self, from: data) {
            expenses = decoded
        }
    }

    private func loadCashflow() {
        let url = dataDirectory.appendingPathComponent("cashflow.json")
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode([CashflowEntry].self, from: data) {
            cashflow = decoded
        }
    }

    // MARK: - Read Financial Data (from workspace files)

    public func readBalance() -> (success: Bool, output: String) {
        let url = dataDirectory.appendingPathComponent("balance.json")
        if let data = try? Data(contentsOf: url),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            var output = "Balance Sheet\n============\n"
            for (key, value) in json.sorted(by: { $0.key < $1.key }) {
                output += "\(key): \(value)\n"
            }
            return (true, output)
        }
        return (false, "No balance.json found in .finance_data/")
    }

    public func readCashflow() -> (success: Bool, output: String) {
        if cashflow.isEmpty {
            return (false, "No cashflow data available")
        }

        var output = "Cashflow Report\n===============\n"
        var totalInflow: Double = 0
        var totalOutflow: Double = 0

        for entry in cashflow.sorted(by: { $0.date < $1.date }) {
            let date = Date(timeIntervalSince1970: entry.date)
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            output += "\(formatter.string(from: date)) \(entry.direction.glyph) \(entry.category): $\(String(format: "%.2f", entry.amount)) — \(entry.description)\n"

            if entry.direction == .inflow {
                totalInflow += entry.amount
            } else {
                totalOutflow += entry.amount
            }
        }

        output += "\nTotal Inflow: $\(String(format: "%.2f", totalInflow))\n"
        output += "Total Outflow: $\(String(format: "%.2f", totalOutflow))\n"
        output += "Net: $\(String(format: "%.2f", totalInflow - totalOutflow))\n"

        return (true, output)
    }

    public func reviewExpenses() -> (success: Bool, output: String) {
        if expenses.isEmpty {
            return (false, "No expense data available")
        }

        var output = "Expense Review\n==============\n"
        let grouped = Dictionary(grouping: expenses, by: { $0.category })
        var totalExpenses: Double = 0

        for (category, records) in grouped.sorted(by: { $0.value.reduce(0) { $0 + $1.amount } > $1.value.reduce(0) { $0 + $1.amount } }) {
            let categoryTotal = records.reduce(0) { $0 + $1.amount }
            totalExpenses += categoryTotal
            output += "\n\(category.glyph) \(category.rawValue.uppercased()): $\(String(format: "%.2f", categoryTotal)) (\(records.count) items)\n"
            for record in records.sorted(by: { $0.amount > $1.amount }).prefix(5) {
                output += "  $\(String(format: "%.2f", record.amount)) — \(record.description)\(record.recurring ? " [recurring]" : "")\n"
            }
        }

        output += "\nTotal Expenses: $\(String(format: "%.2f", totalExpenses))\n"

        // Identify top spending categories
        let topCategory = grouped.max { $0.value.reduce(0) { $0 + $1.amount } < $1.value.reduce(0) { $0 + $1.amount } }
        if let (cat, records) = topCategory {
            let pct = totalExpenses > 0 ? (records.reduce(0) { $0 + $1.amount } / totalExpenses) * 100 : 0
            output += "Top category: \(cat.rawValue) (\(String(format: "%.1f", pct))%)\n"
        }

        return (true, output)
    }

    // MARK: - Create Draft Invoice (writes to workspace, never sends)

    public func createDraftInvoice(clientName: String, clientEmail: String? = nil,
                                    lineItems: [(description: String, quantity: Double, unitPrice: Double)],
                                    taxRate: Double = 0, notes: String? = nil) -> (success: Bool, output: String) {
        let invoiceNumber = "INV-\(String(format: "%04d", invoices.count + 1))"
        let items = lineItems.map { InvoiceLineItem(description: $0.description, quantity: $0.quantity, unitPrice: $0.unitPrice) }

        let invoice = Invoice(
            invoiceNumber: invoiceNumber,
            clientName: clientName,
            clientEmail: clientEmail,
            lineItems: items,
            taxRate: taxRate,
            notes: notes
        )

        invoices.append(invoice)
        saveInvoices()

        var output = "Draft Invoice Created\n=====================\n"
        output += "Invoice #: \(invoice.invoiceNumber)\n"
        output += "Client: \(invoice.clientName)\n"
        output += "Date: \(Date(timeIntervalSince1970: invoice.issueDate))\n"
        output += "Due: \(Date(timeIntervalSince1970: invoice.dueDate))\n"
        output += "\nLine Items:\n"
        for item in invoice.lineItems {
            output += "  \(item.description): \(item.quantity) × $\(String(format: "%.2f", item.unitPrice)) = $\(String(format: "%.2f", item.total))\n"
        }
        output += "\nSubtotal: $\(String(format: "%.2f", invoice.subtotal))\n"
        output += "Tax (\(String(format: "%.1f", invoice.taxRate))%): $\(String(format: "%.2f", invoice.taxAmount))\n"
        output += "Total: $\(String(format: "%.2f", invoice.total))\n"
        output += "\nStatus: DRAFT (not sent — no network access)\n"

        return (true, output)
    }

    // MARK: - Risk Assessment

    public func assessRisk() -> FinanceRiskAssessment {
        let snap = snapshot
        let cash = snap?.cashOnHand ?? 0
        let burn = snap?.monthlyBurn ?? 0
        let runway = snap?.runwayMonths ?? 999
        let outstanding = snap?.outstandingInvoices ?? 0
        let overdue = snap?.overdueInvoices ?? 0
        let margin = snap?.profitMargin ?? 0

        var findings: [FinanceRiskFinding] = []
        var recommendations: [String] = []

        // Cash risk
        let cashRisk: FinanceRiskAssessment.FinanceRiskLevel
        if runway < 3 {
            cashRisk = .severe
            findings.append(FinanceRiskFinding(severity: .severe, category: "cash",
                description: "Runway < 3 months (\(runway) months)",
                impact: "Critical — company may run out of cash"))
            recommendations.append("Immediately reduce burn rate or raise capital")
        } else if runway < 6 {
            cashRisk = .high
            findings.append(FinanceRiskFinding(severity: .high, category: "cash",
                description: "Runway < 6 months (\(runway) months)",
                impact: "High risk — need funding or revenue increase"))
            recommendations.append("Accelerate revenue or secure bridge funding")
        } else if runway < 12 {
            cashRisk = .elevated
            findings.append(FinanceRiskFinding(severity: .elevated, category: "cash",
                description: "Runway < 12 months (\(runway) months)",
                impact: "Moderate risk — plan ahead"))
        } else {
            cashRisk = .low
        }

        // Revenue risk
        let revenueRisk: FinanceRiskAssessment.FinanceRiskLevel
        if margin < 0 {
            revenueRisk = .severe
            findings.append(FinanceRiskFinding(severity: .severe, category: "revenue",
                description: "Negative profit margin (\(String(format: "%.1f", margin))%)",
                impact: "Losing money on every sale"))
            recommendations.append("Increase prices or reduce cost of goods sold")
        } else if margin < 10 {
            revenueRisk = .elevated
            findings.append(FinanceRiskFinding(severity: .elevated, category: "revenue",
                description: "Low profit margin (\(String(format: "%.1f", margin))%)",
                impact: "Thin margins — vulnerable to cost changes"))
        } else {
            revenueRisk = .low
        }

        // Expense risk
        let expenseRisk: FinanceRiskAssessment.FinanceRiskLevel
        let recurringExpenses = expenses.filter { $0.recurring }.reduce(0.0) { $0 + $1.amount }
        if burn > 0 && recurringExpenses / burn > 0.8 {
            expenseRisk = .elevated
            findings.append(FinanceRiskFinding(severity: .elevated, category: "expenses",
                description: "High recurring expense ratio (\(String(format: "%.0f", recurringExpenses / burn * 100))%)",
                impact: "Most expenses are fixed — hard to reduce quickly"))
        } else {
            expenseRisk = .low
        }

        // Invoice risk
        let invoiceRisk: FinanceRiskAssessment.FinanceRiskLevel
        if overdue > 0 && outstanding > 0 {
            let overduePct = (overdue / outstanding) * 100
            if overduePct > 50 {
                invoiceRisk = .high
                findings.append(FinanceRiskFinding(severity: .high, category: "invoices",
                    description: "\(String(format: "%.0f", overduePct))% of outstanding invoices are overdue",
                    impact: "Cash collection problem"))
                recommendations.append("Follow up on overdue invoices immediately")
            } else if overduePct > 25 {
                invoiceRisk = .elevated
                findings.append(FinanceRiskFinding(severity: .elevated, category: "invoices",
                    description: "\(String(format: "%.0f", overduePct))% of outstanding invoices are overdue",
                    impact: "Some collection delays"))
            } else {
                invoiceRisk = .moderate
            }
        } else {
            invoiceRisk = .low
        }

        // Overall risk
        let allRisks = [cashRisk, revenueRisk, expenseRisk, invoiceRisk]
        let overall: FinanceRiskAssessment.FinanceRiskLevel
        if allRisks.contains(.severe) {
            overall = .severe
        } else if allRisks.contains(.high) {
            overall = .high
        } else if allRisks.contains(.elevated) {
            overall = .elevated
        } else if allRisks.contains(.moderate) {
            overall = .moderate
        } else {
            overall = .low
        }

        if recommendations.isEmpty {
            recommendations.append("Financial health looks stable — continue monitoring")
        }

        let assessment = FinanceRiskAssessment(
            overallRisk: overall,
            cashRisk: cashRisk,
            revenueRisk: revenueRisk,
            expenseRisk: expenseRisk,
            invoiceRisk: invoiceRisk,
            findings: findings,
            recommendations: recommendations
        )

        riskAssessment = assessment
        return assessment
    }

    // MARK: - Compute Snapshot

    private func computeSnapshot() {
        let totalRevenue = cashflow.filter { $0.direction == .inflow }.reduce(0.0) { $0 + $1.amount }
        let totalExpenses = cashflow.filter { $0.direction == .outflow }.reduce(0.0) { $0 + $1.amount }
        let outstanding = invoices.filter { $0.status == .sent || $0.status == .overdue }.reduce(0.0) { $0 + $1.total }
        let overdue = invoices.filter { $0.status == .overdue }.reduce(0.0) { $0 + $1.total }
        let monthlyBurn = expenses.filter { $0.recurring }.reduce(0.0) { $0 + $1.amount }
        let cashOnHand = totalRevenue - totalExpenses

        snapshot = FinancialSnapshot(
            totalRevenue: totalRevenue,
            totalExpenses: totalExpenses,
            cashOnHand: cashOnHand,
            outstandingInvoices: outstanding,
            overdueInvoices: overdue,
            monthlyBurn: monthlyBurn
        )
    }

    // MARK: - Save Data

    private func saveInvoices() {
        let url = dataDirectory.appendingPathComponent("invoices.json")
        if let data = try? JSONEncoder().encode(invoices) {
            try? data.write(to: url)
        }
    }

    // MARK: - Summary

    public var summary: String {
        if let snap = snapshot {
            return "Finance: Revenue $\(String(format: "%.0f", snap.totalRevenue)) | Expenses $\(String(format: "%.0f", snap.totalExpenses)) | Net $\(String(format: "%.0f", snap.netProfit)) | Runway \(snap.runwayMonths)mo | \(invoices.count) invoices"
        }
        return "Finance: No data loaded"
    }

    // MARK: - CSV Parser (for importing financial data)

    public func parseCSV(_ content: String) -> [[String]] {
        let rows = content.components(separatedBy: "\n").filter { !$0.isEmpty }
        return rows.map { row in
            row.components(separatedBy: ",")
        }
    }

    // MARK: - Import Expenses from CSV

    public func importExpensesFromCSV(_ content: String) -> (success: Bool, count: Int) {
        let rows = parseCSV(content)
        guard rows.count > 1 else { return (false, 0) }

        var imported = 0
        for row in rows.dropFirst() {
            guard row.count >= 4 else { continue }
            let category = ExpenseRecord.ExpenseCategory(rawValue: row[0].trimmingCharacters(in: .whitespaces)) ?? .other
            let description = row[1].trimmingCharacters(in: .whitespaces)
            let amount = Double(row[2].trimmingCharacters(in: .whitespaces)) ?? 0
            let dateStr = row[3].trimmingCharacters(in: .whitespaces)

            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            let date = formatter.date(from: dateStr)?.timeIntervalSince1970 ?? Date().timeIntervalSince1970

            expenses.append(ExpenseRecord(date: date, category: category,
                                          description: description, amount: amount))
            imported += 1
        }

        if imported > 0 {
            saveExpenses()
            computeSnapshot()
        }

        return (true, imported)
    }

    private func saveExpenses() {
        let url = dataDirectory.appendingPathComponent("expenses.json")
        if let data = try? JSONEncoder().encode(expenses) {
            try? data.write(to: url)
        }
    }

    // MARK: - Export Report

    public func exportReport() -> String {
        var report = "FINANCIAL REPORT\n"
        report += "================\n"
        report += "Generated: \(Date())\n\n"

        if let snap = snapshot {
            report += "SUMMARY\n"
            report += "-------\n"
            report += "Total Revenue: $\(String(format: "%.2f", snap.totalRevenue))\n"
            report += "Total Expenses: $\(String(format: "%.2f", snap.totalExpenses))\n"
            report += "Net Profit: $\(String(format: "%.2f", snap.netProfit))\n"
            report += "Profit Margin: \(String(format: "%.1f", snap.profitMargin))%\n"
            report += "Cash on Hand: $\(String(format: "%.2f", snap.cashOnHand))\n"
            report += "Monthly Burn: $\(String(format: "%.2f", snap.monthlyBurn))\n"
            report += "Runway: \(snap.runwayMonths) months\n\n"
        }

        if let risk = riskAssessment {
            report += "RISK ASSESSMENT\n"
            report += "---------------\n"
            report += "Overall: \(risk.overallRisk.glyph) \(risk.overallRisk.rawValue.uppercased())\n"
            for finding in risk.findings {
                report += "  \(finding.severity.glyph) [\(finding.category)] \(finding.description)\n"
            }
            report += "\nRecommendations:\n"
            for rec in risk.recommendations {
                report += "  → \(rec)\n"
            }
        }

        return report
    }
}
