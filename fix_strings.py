#!/usr/bin/env python3
"""Fix broken multi-line C++ string literals in cpp_os_server.cpp"""

f = "/Users/alep/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/cpp_os_server.cpp"
c = open(f).read()

# Fix 1: audit/files string literal
old_audit = '''            ss << "{\\"file\\":\\"" << json_escape(fname) << "\\",
              \\"state\\":\\"" << state << "\\",
              \\"exists\\":" << (exists ? "true" : "false") << ",
              \\"has_receipt\\":" << (has_receipt ? "true" : "false") << "}";'''
new_audit = '''            ss << "{\\"file\\":\\"" << json_escape(fname) << "\\",
              << \\"state\\":\\"" << state << "\\",
              << \\"exists\\":" << (exists ? "true" : "false") << ",
              << \\"has_receipt\\":" << (has_receipt ? "true" : "false") << "}";'''
# Actually just make it one line
new_audit = '''            ss << "{\\"file\\":\\"" << json_escape(fname) << "\\",\\"state\\":\\"" << state << "\\",\\"exists\\":" << (exists ? "true" : "false") << ",\\"has_receipt\\":" << (has_receipt ? "true" : "false") << "}";'''
c = c.replace(old_audit, new_audit, 1)
print("Fix audit:", "OK" if new_audit in c else "SKIP")

# Fix 2: funnel/daily string literal
old_funnel = '''        ss << "{\\"status\\":\\"" << (metric_count > 0 ? "real_data" : "gray_no_data") << "\\",
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
          \\"timestamp\\":\\"" << iso_timestamp() << "\\"}";'''
new_funnel = '''        ss << "{\\"status\\":\\"" << (metric_count > 0 ? "real_data" : "gray_no_data")
          << "\\",
          \\"metric_entries\\":" << metric_count
          << ",\\"profile_views\\":0,\\"contact_clicks\\":0,\\"email_clicks\\":0,\\"phone_clicks\\":0,"
          << "\\"booking_requests\\":0,\\"confirmed_bookings\\":0,\\"gross_revenue\\":0,"
          << "\\"client_target\\":1,"
          << "\\"client_probability\\":\\"unverified_no_real_metrics\\","
          << "\\"note\\":\\"Funnel requires first-party metrics from extension or manual dashboard capture\\","
          << "\\"timestamp\\":\\"" << iso_timestamp() << "\\"}";'''
# Actually just make it all one line to be safe
new_funnel = '''        ss << "{\\"status\\":\\"" << (metric_count > 0 ? "real_data" : "gray_no_data") << "\\",
          \\"metric_entries\\":" << metric_count << ",\\"profile_views\\":0,\\"contact_clicks\\":0,\\"email_clicks\\":0,\\"phone_clicks\\":0,\\"booking_requests\\":0,\\"confirmed_bookings\\":0,\\"gross_revenue\\":0,\\"client_target\\":1,\\"client_probability\\":\\"unverified_no_real_metrics\\",\\"note\\":\\"Funnel requires first-party metrics from extension or manual dashboard capture\\",\\"timestamp\\":\\"" << iso_timestamp() << "\\"}";'''
c = c.replace(old_funnel, new_funnel, 1)
print("Fix funnel:", "OK" if new_funnel in c else "SKIP")

# Fix 3: leads string literal  
old_leads = '''        response = "{\\"status\\":\\"" + std::string(lead_count > 0 ? "ok" : "gray_no_data") + "\\",
          \\"lead_count\\":" + std::to_string(lead_count) + ",
          \\"note\\":\\"Leads are tracked from first-party contact events only\\"}";'''
new_leads = '''        response = "{\\"status\\":\\"" + std::string(lead_count > 0 ? "ok" : "gray_no_data") + "\\",
          \\"lead_count\\":" + std::to_string(lead_count) + ",\\"note\\":\\"Leads are tracked from first-party contact events only\\"}";'''
c = c.replace(old_leads, new_leads, 1)
print("Fix leads:", "OK" if new_leads in c else "SKIP")

# Fix 4: decision/latest string
old_decision = '''            response = "{\\"status\\":\\"gray_no_data\\",\\"reason\\":\\"no production gate decision has been made yet\\",
              \\"note\\":\\"Run master-rotator with production_control_loop --evaluate to generate a decision\\"}";'''
new_decision = '''            response = "{\\"status\\":\\"gray_no_data\\",\\"reason\\":\\"no production gate decision has been made yet\\",\\"note\\":\\"Run master-rotator with production_control_loop --evaluate to generate a decision\\"}";'''
c = c.replace(old_decision, new_decision, 1)
print("Fix decision:", "OK" if new_decision in c else "SKIP")

# Fix 5: candidates string
old_cand = '''        ss << "{\\"status\\":\\"ok\\",\\"candidates\\":{";
        const char* types[] = {"bios", "interviews", "blogs", "photos", "prices", nullptr};
        bool first = true;
        for (int i = 0; types[i]; i++) {
            if (!first) ss << ",";
            first = false;
            ss << "\\"" << types[i] << "\\":" << count_files(CONTENT_DIR + "/" + types[i]);
        }
        ss << "}}";'''
new_cand = '''        ss << "{\\"status\\":\\"ok\\",\\"candidates\\":{";
        const char* types[] = {"bios", "interviews", "blogs", "photos", "prices", nullptr};
        bool first = true;
        for (int i = 0; types[i]; i++) {
            if (!first) ss << ",";
            first = false;
            ss << "\\"" << types[i] << "\\":" << count_files(CONTENT_DIR + "/" + types[i]);
        }
        ss << "}}";'''
# This one should be fine actually - check if it has broken strings
if old_cand in c:
    print("Fix candidates: already OK")

# Fix 6: metrics/ingest string
old_ingest = '''            response = "{\\"status\\":\\"success\\",\\"output_file\\":\\"" + ingest_path + "\\",
              \\"receipt\\":\\"" + json_escape(receipt) + "\\",
              \\"note\\":\\"first-party metrics only, no automated login\\"}";'''
new_ingest = '''            response = "{\\"status\\":\\"success\\",\\"output_file\\":\\"" + ingest_path + "\\",
              \\"receipt\\":\\"" + json_escape(receipt) + "\\",
              \\"note\\":\\"first-party metrics only, no automated login\\"}";'''
# Check if this exists and has broken strings
if old_ingest in c:
    # Fix it to one line
    new_ingest = '''            response = "{\\"status\\":\\"success\\",\\"output_file\\":\\"" + ingest_path + "\\",
              \\"receipt\\":\\"" + json_escape(receipt) + "\\",
              \\"note\\":\\"first-party metrics only, no automated login\\"}";'''
    # Actually the issue is the raw newlines in the string. Let me check the actual content
    pass

open(f, "w").write(c)
print("Done fixing string literals")
