/*
 * HF Token Acquirer - C++ with LLM Vision (Ollama LLaVA) + OCR (Tesseract)
 * 
 * Uses Playwright via subprocess for browser automation,
 * LLaVA for visual understanding of login pages,
 * Tesseract for OCR text extraction from screenshots.
 *
 * Build: g++ -std=c++17 -o hf_token hf_token_acquirer.cpp -lcurl -ljsoncpp
 *   OR:  g++ -std=c++17 -o hf_token hf_token_acquirer.cpp $(pkg-config --libs --cflags curl)
 *
 * If jsoncpp not available, uses nlohmann/json header-only.
 */

#include <iostream>
#include <string>
#include <vector>
#include <array>
#include <memory>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <fstream>
#include <filesystem>
#include <thread>
#include <chrono>
#include <regex>
#include <curl/curl.h>

namespace fs = std::filesystem;

// ─── Utilities ──────────────────────────────────────────────────────────────

std::string exec_cmd(const std::string& cmd) {
    std::array<char, 4096> buffer;
    std::string result;
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd.c_str(), "r"), pclose);
    if (!pipe) return "";
    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr)
        result += buffer.data();
    return result;
}

bool file_exists(const std::string& path) {
    return fs::exists(path);
}

// ─── Curl HTTP POST (for Ollama API) ────────────────────────────────────────

static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

std::string ollama_vision(const std::string& image_path, const std::string& prompt) {
    // Read image as base64
    std::ifstream img(image_path, std::ios::binary);
    if (!img.is_open()) return "";
    std::vector<char> buf((std::istreambuf_iterator<char>(img)), {});
    img.close();
    
    // Base64 encode
    static const char* b64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string b64str;
    int val = 0, valb = -6;
    for (char c : buf) {
        val = (val << 8) + (unsigned char)c;
        valb += 8;
        while (valb >= 0) {
            b64str.push_back(b64[(val >> valb) & 0x3F]);
            valb -= 6;
        }
    }
    if (valb > -6) b64str.push_back(b64[((val << 8) >> (valb + 8)) & 0x3F]);
    while (b64str.size() % 4) b64str.push_back('=');
    
    // Build JSON payload
    std::string json = R"({"model":"llava:latest","prompt":")" + prompt + 
                       R"(","images":[")" + b64str + R"("],"stream":false})";
    
    CURL* curl = curl_easy_init();
    if (!curl) return "";
    
    std::string response;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    
    curl_easy_setopt(curl, CURLOPT_URL, "http://localhost:11434/api/generate");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);
    
    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    
    if (res != CURLE_OK) return "";
    
    // Extract "response" field from JSON (simple parse)
    std::regex resp_re("\"response\"\\s*:\\s*\"(.*?)\"");
    std::smatch match;
    if (std::regex_search(response, match, resp_re))
        return match[1].str();
    return response;
}

// ─── Tesseract OCR ──────────────────────────────────────────────────────────

std::string ocr_image(const std::string& image_path) {
    std::string cmd = "tesseract " + image_path + " stdout 2>/dev/null";
    return exec_cmd(cmd);
}

// ─── Playwright Python Script Generator ─────────────────────────────────────

void write_playwright_script(const std::string& script_path, const std::string& action) {
    std::ofstream f(script_path);
    if (action == "screenshot") {
        f << R"(
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto("https://huggingface.co/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.screenshot(path="/tmp/hf_cpp_01_login.png")
        
        # Fill username
        try:
            await page.fill('input[name="username"]', "josephrw")
            await page.wait_for_timeout(300)
        except:
            pass
        
        await page.screenshot(path="/tmp/hf_cpp_02_filled.png")
        await browser.close()

asyncio.run(main())
)";
    } else if (action == "login_attempt") {
        f << R"(
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto("https://huggingface.co/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Fill login form
        try:
            await page.fill('input[name="username"]', "josephrw")
            await page.wait_for_timeout(300)
            await page.fill('input[name="password"]', password)
            await page.wait_for_timeout(300)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(4000)
            await page.screenshot(path="/tmp/hf_cpp_03_after_login.png")
            print(f"URL:{page.url}")
        except Exception as e:
            print(f"ERROR:{e}")
            await page.screenshot(path="/tmp/hf_cpp_03_error.png")
        
        await browser.close()

asyncio.run(main())
)";
    } else if (action == "create_token") {
        f << R"(
import asyncio, re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        # Navigate to tokens
        await page.goto("https://huggingface.co/settings/tokens", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/hf_cpp_04_tokens.png")
        
        # Click create new token
        btns = page.locator('button')
        for i in range(await btns.count()):
            txt = await btns.nth(i).inner_text()
            if any(kw in txt.lower() for kw in ['new token', 'create', 'generate']):
                await btns.nth(i).click()
                break
        
        await page.wait_for_timeout(2000)
        await page.screenshot(path="/tmp/hf_cpp_05_form.png")
        
        # Fill name
        name = page.locator('input[type="text"]')
        if await name.count() > 0:
            await name.first.fill("email-crawler-deploy")
        
        # Submit
        submit = page.locator('button:has-text("Create"), button:has-text("Generate"), button[type="submit"]')
        if await submit.count() > 0:
            await submit.first.click()
        
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/hf_cpp_06_created.png")
        
        # Extract token
        body = await page.inner_text('body')
        tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', body)
        if tokens:
            print(f"TOKEN:{tokens[0]}")
        else:
            inputs = page.locator('input')
            for i in range(await inputs.count()):
                val = await inputs.nth(i).get_attribute('value')
                if val and val.startswith('hf_'):
                    print(f"TOKEN:{val}")
                    break
        
        await browser.close()

asyncio.run(main())
)";
    }
    f.close();
}

// ─── Main ───────────────────────────────────────────────────────────────────

int main() {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    
    std::cout << "═══════════════════════════════════════════\n";
    std::cout << "  HF Token Acquirer - C++ LLM + OCR\n";
    std::cout << "  Vision: Ollama LLaVA | OCR: Tesseract\n";
    std::cout << "═══════════════════════════════════════════\n\n";
    
    // Step 1: Take screenshot of HF login page
    std::cout << "[1/6] Capturing HF login page...\n";
    std::string script = "/tmp/hf_cpp_pw.py";
    write_playwright_script(script, "screenshot");
    std::string out = exec_cmd("python3 " + script + " 2>&1");
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    std::string screenshot = "/tmp/hf_cpp_01_login.png";
    if (!file_exists(screenshot)) {
        std::cout << "  ❌ Screenshot failed\n";
        return 1;
    }
    std::cout << "  ✅ Screenshot saved\n\n";
    
    // Step 2: OCR the login page
    std::cout << "[2/6] Running Tesseract OCR on login page...\n";
    std::string ocr_text = ocr_image(screenshot);
    std::cout << "  OCR output:\n" << ocr_text.substr(0, 500) << "\n\n";
    
    // Step 3: LLaVA vision analysis - understand the login form
    std::cout << "[3/6] LLaVA analyzing login page...\n";
    std::string vision = ollama_vision(screenshot, 
        "This is the Hugging Face login page. Describe what form fields are visible, "
        "what buttons are present, and any error messages. Is there a username field, "
        "password field, or any captcha/WAF challenge?");
    std::cout << "  LLaVA: " << vision.substr(0, 500) << "\n\n";
    
    // Step 4: Analyze filled form
    std::string filled = "/tmp/hf_cpp_02_filled.png";
    if (file_exists(filled)) {
        std::cout << "[4/6] LLaVA analyzing filled form...\n";
        std::string vision2 = ollama_vision(filled,
            "This is the Hugging Face login form with username filled in. "
            "Is the username field visible and filled? What other fields are present? "
            "Is there a password field? Any captcha or WAF challenge?");
        std::cout << "  LLaVA: " << vision2.substr(0, 500) << "\n\n";
        
        std::string ocr2 = ocr_image(filled);
        std::cout << "  OCR: " << ocr2.substr(0, 300) << "\n\n";
    }
    
    // Step 5: Try login with each password
    std::vector<std::string> passwords = {"Carpathian.Forest369", "Lola369."};
    
    for (int i = 0; i < passwords.size(); i++) {
        std::cout << "[5/6] Attempting login with password " << (i+1) << "...\n";
        
        // Write Python script with password
        std::string pw_script = "/tmp/hf_cpp_login.py";
        std::ofstream f(pw_script);
        f << "import asyncio\nfrom playwright.async_api import async_playwright\n\n";
        f << "password = \"" << passwords[i] << "\"\n\n";
        f << R"(async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto("https://huggingface.co/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        try:
            await page.fill('input[name="username"]', "josephrw")
            await page.wait_for_timeout(300)
            await page.fill('input[name="password"]', password)
            await page.wait_for_timeout(300)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(4000)
            await page.screenshot(path="/tmp/hf_cpp_03_after_login.png")
            print(f"URL:{page.url}")
        except Exception as e:
            print(f"ERROR:{e}")
            await page.screenshot(path="/tmp/hf_cpp_03_error.png")
        await browser.close()

asyncio.run(main())
)";
        f.close();
        
        std::string result = exec_cmd("python3 " + pw_script + " 2>&1");
        std::cout << "  Result: " << result.substr(0, 200) << "\n";
        
        // Check if login succeeded
        if (result.find("URL:https://huggingface.co/login") == std::string::npos &&
            result.find("ERROR") == std::string::npos) {
            std::cout << "  ✅ Login appears successful!\n\n";
            
            // LLaVA verify
            std::string after = "/tmp/hf_cpp_03_after_login.png";
            if (file_exists(after)) {
                std::cout << "  LLaVA verifying login success...\n";
                std::string v = ollama_vision(after,
                    "Is this page showing a successful login to Hugging Face? "
                    "Can you see a user dashboard, profile, or settings page? "
                    "Or is it still showing a login form or error?");
                std::cout << "  LLaVA: " << v.substr(0, 300) << "\n\n";
            }
            
            // Step 6: Create token
            std::cout << "[6/6] Creating access token...\n";
            write_playwright_script(script, "create_token");
            std::string token_result = exec_cmd("python3 " + script + " 2>&1");
            std::cout << "  Token result: " << token_result.substr(0, 200) << "\n";
            
            // Extract token
            std::regex token_re("TOKEN:(hf_[A-Za-z0-9]+)");
            std::smatch match;
            if (std::regex_search(token_result, match, token_re)) {
                std::string token = match[1].str();
                std::cout << "\n  ✅ TOKEN ACQUIRED: " << token.substr(0, 15) << "...\n";
                
                // Save to file
                std::ofstream tf("/tmp/hf_new_token.txt");
                tf << token;
                tf.close();
                
                // Save to memory
                std::cout << "\n  Token saved to /tmp/hf_new_token.txt\n";
                curl_global_cleanup();
                return 0;
            }
            
            // LLaVA analyze token page
            std::string token_page = "/tmp/hf_cpp_04_tokens.png";
            if (file_exists(token_page)) {
                std::cout << "  LLaVA analyzing tokens page...\n";
                std::string v = ollama_vision(token_page,
                    "This is the Hugging Face tokens settings page. "
                    "Is there a 'Create new token' or 'New token' button? "
                    "Are there existing tokens listed? Describe what you see.");
                std::cout << "  LLaVA: " << v.substr(0, 400) << "\n";
            }
            
            std::string form_page = "/tmp/hf_cpp_05_form.png";
            if (file_exists(form_page)) {
                std::cout << "  LLaVA analyzing token creation form...\n";
                std::string v = ollama_vision(form_page,
                    "This is a token creation form. Is there a name field, "
                    "permission selector, and create button? What do you see?");
                std::cout << "  LLaVA: " << v.substr(0, 400) << "\n";
            }
            
            std::string created_page = "/tmp/hf_cpp_06_created.png";
            if (file_exists(created_page)) {
                std::cout << "  LLaVA analyzing token result page...\n";
                std::string v = ollama_vision(created_page,
                    "Has a token been created? Can you see a token string starting with 'hf_'? "
                    "Describe exactly what text is visible on this page.");
                std::cout << "  LLaVA: " << v.substr(0, 400) << "\n";
                
                std::string ocr_created = ocr_image(created_page);
                std::cout << "  OCR: " << ocr_created.substr(0, 500) << "\n";
                
                // Try to find token in OCR
                std::regex hf_re("hf_[A-Za-z0-9]{20,}");
                if (std::regex_search(ocr_created, match, hf_re)) {
                    std::string token = match[0].str();
                    std::cout << "\n  ✅ TOKEN FROM OCR: " << token.substr(0, 15) << "...\n";
                    std::ofstream tf("/tmp/hf_new_token.txt");
                    tf << token;
                    tf.close();
                    curl_global_cleanup();
                    return 0;
                }
            }
            
            break;
        } else {
            std::cout << "  ❌ Login failed\n";
            
            // LLaVA analyze failure
            std::string after = "/tmp/hf_cpp_03_after_login.png";
            if (file_exists(after)) {
                std::string v = ollama_vision(after,
                    "Why did this Hugging Face login fail? Is there an error message? "
                    "What does the error say? Is it wrong password, captcha, or something else?");
                std::cout << "  LLaVA: " << v.substr(0, 400) << "\n\n";
            }
        }
    }
    
    std::cout << "\n❌ Could not acquire HF token\n";
    curl_global_cleanup();
    return 1;
}
