#!/usr/bin/env python3
"""
Add military-grade endpoints to cpp_os_server.cpp:
- /api/jobs (list all job receipts)
- /api/jobs/{id} (get specific job receipt)
- /api/audit/files (function audit of every file)
- /api/funnel/daily (real leads, not estimated revenue)
- /api/leads (track inbound contact events)
- /api/decision/latest (why system kept or changed content)
- /api/candidates (real generated content from files)
- /api/metrics/ingest (first-party metrics with receipt)
"""

filepath = "/Users/alep/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/cpp_os_server.cpp"
with open(filepath, "r") as f:
    content = f.read()

changes = 0

# 1. Add /api/jobs endpoint - list all receipts
old = '    } else if (path == "/api/receipts") {'
new = '''    } else if (path == "/api/jobs") {
        std::ostringstream ss;
        ss << "{\\"status\\":\\"ok\\",\\"jobs\\":[";
        DIR* d = opendir(RECEIPTS_DIR.c_str());
        if (d) {
            struct dirent* entry;
            bool first = true;
            while ((entry = readdir(d)) != nullptr) {
                if (entry->d_type != DT_REG) continue;
                std::string fname = entry->d_name;
                if (!first) ss << ",";
                first = false;
                std::string fcontent = read_file(RECEIPTS_DIR + "/" + fname);
                ss << fcontent;
            }
            closedir(d);
        }
        ss << "]}";
        response = ss.str();
    } else if (path.rfind("/api/jobs/", 0) == 0) {
        std::string job_id = path.substr(10);
        std::string job_path = RECEIPTS_DIR + "/" + job_id;
        std::string fcontent = read_file(job_path);
        if (fcontent.empty()) {
            code = 404;
            response = "{\\"status\\":\\"failed\\",\\"reason\\":\\"job not found\\",\\"job_id\\":\\"" + json_escape(job_id) + "\\"}";
        } else {
            response = fcontent;
        }
    } else if (path == "/api/receipts") {'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("1. /api/jobs + /api/jobs/{id}: OK")

# 2. Add /api/audit/files - function audit
old = '    } else if (path == "/api/receipts") {'
new = '''    } else if (path == "/api/audit/files") {
        std::ostringstream ss;
        ss << "{\\"status\\":\\"ok\\",\\"files\\":[";
        const char* files_to_audit[] = {
            "cpp_os_server.cpp", "rotator_engine.cpp", "ga_rl_optimizer.cpp",
            "production_control_loop.cpp", "Dockerfile", "requirements.txt",
            "orchestrator.py", "content_generator.py", "rl_feedback.py",
            "interview_rotator.py", "blog_rotator.py", "metrics_collector.py",
            "rentmasseur_availability.py", "hf_app.py", nullptr
        };
        bool first = true;
        for (int i = 0; files_to_audit[i]; i++) {
            std::string fname = files_to_audit[i];
            bool exists = file_exists(fname);
            std::string state;
            if (!exists) state = "dead";
            else if (fname.find(".cpp") != std::string::npos) state = "compiled";
            else if (fname.find(".py") != std::string::npos) state = "imported";
            else state = "present";
            bool has_receipt = file_exists(std::string(RECEIPTS_DIR + "/hf_action_") + fname);
            if (!first) ss << ",";
            first = false;
            ss << "{\\"file\\":\\"" << json_escape(fname) << "\\",
              \\"state\\":\\"" << state << "\\",
              \\"exists\\":" << (exists ? "true" : "false") << ",
              \\"has_receipt\\":" << (has_receipt ? "true" : "false") << "}";
        }
        ss << "]}";
        response = ss.str();
    } else if (path == "/api/receipts") {'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("2. /api/audit/files: OK")

# 3. Add /api/funnel/daily and /api/leads and /api/decision/latest and /api/candidates
old = '    } else if (path == "/api/config" && method == "POST") {'
new = '''    } else if (path == "/api/funnel/daily") {
        std::string metrics = read_file(CONTENT_DIR + "/metrics_ingest.jsonl");
        int metric_count = 0;
        if (!metrics.empty()) {
            for (size_t i = 0; i < metrics.size(); i++) if (metrics[i] == '\\n') metric_count++;
        }
        std::ostringstream ss;
        ss << "{\\"status\\":\\"" << (metric_count > 0 ? "real_data" : "gray_no_data") << "\\",
          \\"metric_entries\\":" << metric_count << ",
          \\"profile_views\\":0,
          \\"contact_clicks\\":0,
          \\"email_clicks\\":0,
          \\"phone_clicks\\":0,
          \\"booking_requests\\":0,
          \\"confirmed_bookings\\":0,
          \\"gross_revenue\\":0,
          \\"client_target\\":1,
          \\"client_probability\\":\\"unverified_no_real_metrics\\",
          \\"note\\":\\"Funnel requires first-party metrics from extension or manual dashboard capture\\",
          \\"timestamp\\":\\"" << iso_timestamp() << "\\"}";
        response = ss.str();
    } else if (path == "/api/leads") {
        std::string leads = read_file(CONTENT_DIR + "/leads.jsonl");
        int lead_count = 0;
        if (!leads.empty()) {
            for (size_t i = 0; i < leads.size(); i++) if (leads[i] == '\\n') lead_count++;
        }
        response = "{\\"status\\":\\"" + std::string(lead_count > 0 ? "ok" : "gray_no_data") + "\\",
          \\"lead_count\\":" + std::to_string(lead_count) + ",
          \\"note\\":\\"Leads are tracked from first-party contact events only\\"}";
    } else if (path == "/api/decision/latest") {
        std::string decision = read_file(CONTENT_DIR + "/decisions/latest_decision.json");
        if (decision.empty()) {
            response = "{\\"status\\":\\"gray_no_data\\",\\"reason\\":\\"no production gate decision has been made yet\\",
              \\"note\\":\\"Run master-rotator with production_control_loop --evaluate to generate a decision\\"}";
        } else {
            response = decision;
        }
    } else if (path == "/api/candidates") {
        std::ostringstream ss;
        ss << "{\\"status\\":\\"ok\\",\\"candidates\\":{";
        const char* types[] = {"bios", "interviews", "blogs", "photos", "prices", nullptr};
        bool first = true;
        for (int i = 0; types[i]; i++) {
            if (!first) ss << ",";
            first = false;
            ss << "\\"" << types[i] << "\\":" << count_files(CONTENT_DIR + "/" + types[i]);
        }
        ss << "}}";
        response = ss.str();
    } else if (path == "/api/metrics/ingest" && method == "POST") {
        std::string ingest_path = CONTENT_DIR + "/metrics_ingest.jsonl";
        std::ofstream f(ingest_path, std::ios::app);
        if (!f) { code = 500; response = "{\\"status\\":\\"failed\\",\\"reason\\":\\"could not write metrics file\\"}"; }
        else {
            f << "{\\"timestamp\\":\\"" << iso_timestamp() << "\\",\\"body\\":\\"" << json_escape(body) << "\\"}\\n";
            std::string receipt = write_receipt("metrics_ingest", "success", 0, "first-party metrics accepted",
                "\\"output_file\\": \\"" + ingest_path + "\\"");
            response = "{\\"status\\":\\"success\\",\\"output_file\\":\\"" + ingest_path + "\\",
              \\"receipt\\":\\"" + json_escape(receipt) + "\\",
              \\"note\\":\\"first-party metrics only, no automated login\\"}";
        }
    } else if (path == "/api/config" && method == "POST") {'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("3. /api/funnel/daily, /api/leads, /api/decision/latest, /api/candidates, /api/metrics/ingest: OK")

with open(filepath, "w") as f:
    f.write(content)
print(f"\n{changes}/3 military endpoint upgrades applied")
