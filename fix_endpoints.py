#!/usr/bin/env python3
"""Fix mock/fake endpoints in cpp_os_server.cpp to be receipt-based."""
import re

filepath = "/Users/alep/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/cpp_os_server.cpp"
with open(filepath, "r") as f:
    content = f.read()

fixes_applied = 0

# Fix 1: /api/bios — hardcoded empty array -> read real files
old_bios = '        response = "{\\"bios\\":[]}";'
if old_bios in content:
    new_bios = '''        {
            std::string bios_json = "[";
            DIR* d = opendir((CONTENT_DIR + "/bios").c_str());
            if (d) {
                struct dirent* entry;
                bool first = true;
                while ((entry = readdir(d)) != nullptr) {
                    if (entry->d_type == DT_REG && std::string(entry->d_name).find(".json") != std::string::npos) {
                        if (!first) bios_json += ",";
                        first = false;
                        std::string fpath = CONTENT_DIR + "/bios/" + entry->d_name;
                        std::string fcontent = read_file(fpath);
                        bios_json += fcontent;
                    }
                }
                closedir(d);
            }
            bios_json += "]";
            response = bios_json;
        }'''
    content = content.replace(old_bios, new_bios)
    fixes_applied += 1
    print("Fix 1 (bios): OK")
else:
    print("Fix 1 (bios): SKIP - not found")

# Fix 2: /api/report — add real state files
old_report = '''        std::string rl_state = load_json_or_empty(CONTENT_DIR + "/rl_state.json");
        std::string ga_state = load_json_or_empty(CONTENT_DIR + "/ga_state.json");
        std::string availability = load_json_or_empty(AVAILABILITY_FILE);
        std::ostringstream ss;
        ss << "{\\"rl_state\\":" << rl_state << ","
           << "\\"ga_state\\":" << ga_state << ","
           << "\\"availability\\":" << availability << ","
           << "\\"content_counts\\":{"
           << "\\"bios\\":" << count_files(CONTENT_DIR + "/bios")
           << "},"
           << "\\"timestamp\\":\\"" << iso_timestamp() << "\\""
           << "}";'''
if old_report in content:
    new_report = '''        std::string rl_state = load_json_or_empty(CONTENT_DIR + "/rl_state.json");
        std::string ga_state = load_json_or_empty(CONTENT_DIR + "/ga_state.json");
        std::string availability = load_json_or_empty(AVAILABILITY_FILE);
        std::string metrics_summary = load_json_or_empty(CONTENT_DIR + "/metrics_summary.json");
        std::string system_config = load_json_or_empty(CONTENT_DIR + "/system_config.json");
        std::string latest_decision = load_json_or_empty(CONTENT_DIR + "/decisions/latest_decision.json");
        std::ostringstream ss;
        ss << "{\\"rl_state\\":" << rl_state << ","
           << "\\"ga_state\\":" << ga_state << ","
           << "\\"availability\\":" << availability << ","
           << "\\"metrics_summary\\":" << metrics_summary << ","
           << "\\"system_config\\":" << system_config << ","
           << "\\"latest_decision\\":" << latest_decision << ","
           << "\\"content_counts\\":{"
           << "\\"bios\\":" << count_files(CONTENT_DIR + "/bios") << ","
           << "\\"interviews\\":" << count_files(CONTENT_DIR + "/interviews") << ","
           << "\\"blogs\\":" << count_files(CONTENT_DIR + "/blogs") << ","
           << "\\"photos\\":" << count_files(CONTENT_DIR + "/photos")
           << "},"
           << "\\"timestamp\\":\\"" << iso_timestamp() << "\\""
           << "}";'''
    content = content.replace(old_report, new_report)
    fixes_applied += 1
    print("Fix 2 (report): OK")
else:
    print("Fix 2 (report): SKIP - not found")

# Fix 3: /api/rotate — check data, return blocked or queued with receipt
old_rotate = '''    } else if (path.rfind("/api/rotate/", 0) == 0) {
        std::string rotate_type = path.substr(12);
        std::string cmd = "./rotator_engine --rotate " + rotate_type;
        std::thread([cmd]() { run_command(cmd); }).detach();
        response = "{\\"status\\":\\"started\\",\\"command\\":\\"rotate " + rotate_type + "\\"}";
    } else if (path == "/api/rotator/report") {'''
if old_rotate in content:
    new_rotate = '''    } else if (path.rfind("/api/rotate/", 0) == 0) {
        std::string rotate_type = path.substr(12);
        std::string content_subdir = CONTENT_DIR + "/" + rotate_type;
        int available = count_files(content_subdir);
        if (available == 0) {
            response = "{\\"status\\":\\"blocked\\",\\"reason\\":\\"no_content_available\\",\\"command\\":\\"rotate " + rotate_type + "\\",\\"available_candidates\\":0}";
        } else {
            std::string cmd = "./rotator_engine --rotate " + rotate_type + " 2>&1";
            std::thread([cmd, rotate_type]() {
                std::string out = run_command(cmd);
                std::ofstream log(CONTENT_DIR + "/rotate_" + rotate_type + "_output.log");
                if (log) log << out;
            }).detach();
            response = "{\\"status\\":\\"queued\\",\\"command\\":\\"rotate " + rotate_type + "\\",\\"available_candidates\\":" + std::to_string(available) + ",\\"receipt\\":\\"content/rotate_" + rotate_type + "_output.log\\"}";
        }
    } else if (path == "/api/rotator/report") {'''
    content = content.replace(old_rotate, new_rotate)
    fixes_applied += 1
    print("Fix 3 (rotate): OK")
else:
    print("Fix 3 (rotate): SKIP - not found")

# Fix 4: /api/run/ga-rl
old_ga = '''    } else if (path == "/api/run/ga-rl") {
        std::thread([]() {
            run_command("./ga_rl_optimizer --population 12 --generations 5 --target 300");
            run_command("./ga_rl_optimizer --apply-winner");
        }).detach();
        response = "{\\"status\\":\\"started\\",\\"command\\":\\"ga+rl\\"}";
    } else if (path == "/api/run/orchestrator") {'''
if old_ga in content:
    new_ga = '''    } else if (path == "/api/run/ga-rl") {
        std::string ga_state = load_json_or_empty(CONTENT_DIR + "/ga_state.json");
        std::thread([]() {
            std::string out = run_command("./ga_rl_optimizer --population 12 --generations 5 --target 300 2>&1");
            out += run_command("./ga_rl_optimizer --apply-winner 2>&1");
            std::ofstream log(CONTENT_DIR + "/ga_rl_output.log");
            if (log) log << out;
        }).detach();
        response = "{\\"status\\":\\"queued\\",\\"command\\":\\"ga+rl\\",\\"current_state\\":" + ga_state + ",\\"receipt\\":\\"content/ga_rl_output.log\\"}";
    } else if (path == "/api/run/orchestrator") {'''
    content = content.replace(old_ga, new_ga)
    fixes_applied += 1
    print("Fix 4 (ga-rl): OK")
else:
    print("Fix 4 (ga-rl): SKIP - not found")

# Fix 5: /api/run/orchestrator
old_orch = '''    } else if (path == "/api/run/orchestrator") {
        std::thread([]() {
            run_command("python3 orchestrator.py");
        }).detach();
        response = "{\\"status\\":\\"started\\",\\"command\\":\\"orchestrator\\"}";
    } else if (path == "/api/run/availability") {'''
if old_orch in content:
    new_orch = '''    } else if (path == "/api/run/orchestrator") {
        std::thread([]() {
            std::string out = run_command("python3 orchestrator.py 2>&1");
            std::ofstream log(CONTENT_DIR + "/orchestrator_output.log");
            if (log) log << out;
        }).detach();
        response = "{\\"status\\":\\"queued\\",\\"command\\":\\"orchestrator\\",\\"receipt\\":\\"content/orchestrator_output.log\\"}";
    } else if (path == "/api/run/availability") {'''
    content = content.replace(old_orch, new_orch)
    fixes_applied += 1
    print("Fix 5 (orchestrator): OK")
else:
    print("Fix 5 (orchestrator): SKIP - not found")

# Fix 6: /api/run/availability — NO Selenium
old_avail = '''    } else if (path == "/api/run/availability") {
        std::thread([]() {
            run_command("python3 rentmasseur_availability.py --once --headless true");
        }).detach();
        response = "{\\"status\\":\\"started\\",\\"command\\":\\"availability\\"}";
    } else if (path.rfind("/api/rotate/", 0) == 0) {'''
if old_avail in content:
    new_avail = '''    } else if (path == "/api/run/availability") {
        std::thread([]() {
            std::string out = run_command("python3 metrics_collector.py --process 2>&1");
            std::ofstream log(CONTENT_DIR + "/metrics_collector_output.log");
            if (log) log << out;
        }).detach();
        response = "{\\"status\\":\\"queued\\",\\"command\\":\\"metrics_collector\\",\\"note\\":\\"first_party_only_no_automated_login\\",\\"receipt\\":\\"content/metrics_collector_output.log\\"}";
    } else if (path.rfind("/api/rotate/", 0) == 0) {'''
    content = content.replace(old_avail, new_avail)
    fixes_applied += 1
    print("Fix 6 (availability): OK")
else:
    print("Fix 6 (availability): SKIP - not found")

with open(filepath, "w") as f:
    f.write(content)
print(f"\n{fixes_applied}/6 fixes applied")
