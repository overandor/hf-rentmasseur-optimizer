#!/usr/bin/env python3
import sys

f = "/Users/alep/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/cpp_os_server.cpp"
c = open(f).read()
changes = 0

# 1. Admin token env var
old1 = 'static const std::string CONTENT_DIR = "./content";'
new1 = 'static std::string ADMIN_TOKEN = std::getenv("ADMIN_TOKEN") ? std::getenv("ADMIN_TOKEN") : "";\nstatic const std::string CONTENT_DIR = "./content";'
if old1 in c:
    c = c.replace(old1, new1, 1)
    changes += 1
    print("1. Admin token env: OK")

# 2. Admin check functions before landing_page
old2 = 'static std::string landing_page() {'
new2 = """static bool is_mutation(const std::string& m, const std::string& p) {
    if (m == "POST") return true;
    if (p.rfind("/api/cicd/trigger/", 0) == 0) return true;
    if (p.rfind("/api/rotate/", 0) == 0) return true;
    if (p == "/api/run/ga-rl" || p == "/api/run/orchestrator" || p == "/api/run/availability" || p == "/api/rotator/report") return true;
    return false;
}

static std::string check_admin(const std::string& req, const std::string& path, const std::string& method) {
    if (!is_mutation(method, path)) return "";
    if (ADMIN_TOKEN.empty()) return "";
    size_t ap = req.find("Authorization: Bearer ");
    if (ap != std::string::npos) {
        size_t vs = ap + 21;
        size_t ve = req.find("\\r\\n", vs);
        if (req.substr(vs, ve - vs) == ADMIN_TOKEN) return "";
    }
    size_t qp = path.find("?token=");
    if (qp != std::string::npos && path.substr(qp + 7) == ADMIN_TOKEN) return "";
    return blocked_response("auth", "Admin token required for mutation endpoints. Set ADMIN_TOKEN env var.");
}

static std::string landing_page() {"""
if old2 in c:
    c = c.replace(old2, new2, 1)
    changes += 1
    print("2. Admin check functions: OK")

# 3. Admin check in handle_client
old3 = '    if (method == "OPTIONS") {'
new3 = """    std::string auth_err = check_admin(request, path, method);
    if (!auth_err.empty()) {
        code = 403;
        response = auth_err;
        std::string w = http_response(code, content_type, response);
        send(client_socket, w.c_str(), w.size(), 0);
        close(client_socket);
        return;
    }

    if (method == "OPTIONS") {"""
if old3 in c:
    c = c.replace(old3, new3, 1)
    changes += 1
    print("3. Admin check in handler: OK")

# 4. Status labels in action_response
old4 = '    std::string status = r.exit_code == 0 ? "success" : "failed";'
new4 = '    std::string status = r.exit_code == 0 ? "success" : "failed";\n    std::string label = r.exit_code == 0 ? (!r.output.empty() ? "GREEN_REAL" : "GRAY_NO_DATA") : "RED_FAILED";'
if old4 in c:
    c = c.replace(old4, new4, 1)
    changes += 1
    print("4. Status label var: OK")

# 5. Add label to action_response JSON
old5 = '    ss << "{\\"status\\":\\"' + '"' + '" << status << "\\"'
# This is tricky - let me find the actual line
import re
# Find the action_response JSON output line
match = re.search(r'ss << "\{\\"status\\":\\"\\" << status << "\\",\\"action', c)
if match:
    old5 = match.group()
    new5 = old5.replace('"action', '"label\\":\\"' + '" << label << "\\","action')
    c = c.replace(old5, new5, 1)
    changes += 1
    print("5. Label in JSON: OK")
else:
    print("5. Label in JSON: SKIP - pattern not found")

open(f, "w").write(c)
print(f"\n{changes}/5 military upgrades applied")
