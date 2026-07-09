#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <random>
#include <chrono>
#include <sstream>

std::vector<std::string> headlines = {
    "Deep Tissue & {thing} — Manhattan",
    "{adjective} Bodywork in Manhattan",
    "{name} Does {thing} — Manhattan",
    "The Wolf's {thing} — Manhattan",
    "{thing} for {person} — Manhattan",
    "Manhattan's {adjective} {thing}",
    "Not Your Average {thing} — Manhattan",
    "Real {thing} for {person}",
    "{thing}: No Fluff, Just Pressure",
    "Bring the {body_part}, Bring the Wolf — Manhattan",
    "{adjective} {thing} in Manhattan, NYC",
    "The {person}'s {thing} — Manhattan",
    "Wolf-Level {thing} — Manhattan",
    "{body_part} Rescue in Manhattan",
    "From {city} Stress to {thing}",
};

std::vector<std::string> hooks = {
    "Your shoulders called. They want out of this meeting.",
    "I don't do feathers. I do fixes.",
    "You bring the stress, I bring the Wolf.",
    "If your body were a group chat, your hips would be the one screaming.",
    "Some people meditate. I prefer pressure.",
    "Desk life: 1. Your posture: 0. I can fix that.",
    "Your back is not a storage unit for stress.",
    "I work on humans, not mannequins.",
    "The gym builds muscle. I build recovery.",
    "Tight neck? Tight shoulders? Tight everything? Same.",
    "Wolf knows where the knots hide.",
    "You can't out-train bad recovery, but you can out-massage it.",
    "Manhattan is stressful. Your body doesn't have to be.",
    "My hands are GPS for tension.",
    "If your muscles wrote a Yelp review, it would not be five stars.",
    "I find the thing that hurts and make it stop hurting.",
    "Your body is a resume. Let's edit it.",
    "Squats gave you glutes. I give them back their range of motion.",
    "The only thing I ghost is tension.",
    "I've got strong hands and zero patience for bad posture.",
};

std::vector<std::string> specialties = {
    "I specialize in deep tissue, sports recovery, and targeted relief for shoulders, neck, back, and hips.",
    "My focus is pressure-forward work: slow, deliberate, and built around the muscle groups that actually need it.",
    "I do deep tissue, recovery bodywork, and the kind of pressure that actually changes how you move.",
    "Sports recovery, deep tissue, and hip/glute work are my main zones.",
    "I work on the tension that builds from training, travel, and ten-hour desk days.",
};

std::vector<std::string> clients = {
    "Best for lifters, runners, desk workers, and anyone who treats their body like a rental.",
    "Great if you sit all day, train hard, or fly too much.",
    "If your neck feels like a phone cord from 1997, you're my people.",
    "For clients who want real pressure, clear communication, and a clean space.",
    "You don't need to be an athlete. You need to be tight.",
};

std::vector<std::string> styles = {
    "My style is direct. I find the tension, apply pressure, and stay there until it releases.",
    "No spa music required. No fluffy rituals. Just focused work.",
    "I adjust pressure to your body, not a script.",
    "Strong hands, calm presence, zero attitude.",
    "I work with intention. Every minute has a target.",
};

std::vector<std::string> proofs = {
    "Clients usually leave looser, taller, and less hostile toward their desk.",
    "The feedback I get most: 'I should have done this months ago.'",
    "One session won't fix ten years of bad posture, but it's a solid opening argument.",
    "I don't promise magic. I promise real pressure in the right places.",
};

std::vector<std::string> ctas = {
    "Message me with your focus areas and we'll get you sorted.",
    "Manhattan incall. Text or email to book.",
    "Clean private space in Manhattan. DM me to set something up.",
    "If your body is ready, so am I. Message for availability.",
    "Book a session and let's make your muscles less dramatic.",
};

std::vector<std::string> things = {
    "Sports Recovery", "Deep Tissue", "Bodywork", "Knot Removal", "Recovery",
    "Shoulder Rescue", "Hip Relief", "Back Therapy", "Desk Detox", "Stress Reset",
};

std::vector<std::string> adjectives = {
    "Serious", "Pressure-Forward", "Wolf-Approved", "No-Nonsense", "Focused",
    "Real", "Direct", "Professional", "High-Octane", "Tension-Finding",
};

std::vector<std::string> persons = {
    "Desk Workers", "Athletes", "Gym Rats", "Frequent Flyers", "Tired Humans",
    "Shoulders", "Hips", "Runners", "Lifters", "Stressed New Yorkers",
};

std::vector<std::string> body_parts = {
    "Shoulders", "Back", "Hips", "Neck", "Glutes",
};

std::vector<std::string> cities = {
    "Manhattan", "Midtown", "Chelsea", "Hell's Kitchen", "NYC",
};

std::vector<std::string> names = {
    "The Wolf", "Karpathian Wolf", "Wolf", "This Guy",
};

std::string replace_all(std::string str, const std::string& from, const std::string& to) {
    size_t start_pos = 0;
    while((start_pos = str.find(from, start_pos)) != std::string::npos) {
        str.replace(start_pos, from.length(), to);
        start_pos += to.length();
    }
    return str;
}

std::string generate_headline(std::mt19937& rng) {
    std::uniform_int_distribution<int> dist(0, headlines.size() - 1);
    std::string h = headlines[dist(rng)];
    h = replace_all(h, "{thing}", things[std::uniform_int_distribution<int>(0, things.size()-1)(rng)]);
    h = replace_all(h, "{adjective}", adjectives[std::uniform_int_distribution<int>(0, adjectives.size()-1)(rng)]);
    h = replace_all(h, "{name}", names[std::uniform_int_distribution<int>(0, names.size()-1)(rng)]);
    h = replace_all(h, "{person}", persons[std::uniform_int_distribution<int>(0, persons.size()-1)(rng)]);
    h = replace_all(h, "{body_part}", body_parts[std::uniform_int_distribution<int>(0, body_parts.size()-1)(rng)]);
    h = replace_all(h, "{city}", cities[std::uniform_int_distribution<int>(0, cities.size()-1)(rng)]);
    return h;
}

std::string generate_description(std::mt19937& rng) {
    std::string hook = hooks[std::uniform_int_distribution<int>(0, hooks.size()-1)(rng)];
    std::string specialty = specialties[std::uniform_int_distribution<int>(0, specialties.size()-1)(rng)];
    std::string client = clients[std::uniform_int_distribution<int>(0, clients.size()-1)(rng)];
    std::string style = styles[std::uniform_int_distribution<int>(0, styles.size()-1)(rng)];
    std::string proof = proofs[std::uniform_int_distribution<int>(0, proofs.size()-1)(rng)];
    std::string cta = ctas[std::uniform_int_distribution<int>(0, ctas.size()-1)(rng)];

    std::uniform_int_distribution<int> template_dist(0, 1);
    if (template_dist(rng) == 0) {
        return hook + "\n\n" + specialty + "\n\n" + client + "\n\n" + style + "\n\n" + cta;
    }
    return hook + "\n\n" + style + "\n\n" + specialty + "\n\n" + proof + "\n\n" + cta;
}

std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += c;
        }
    }
    return out;
}

int main(int argc, char* argv[]) {
    int count = 1000;
    if (argc > 1) count = std::stoi(argv[1]);

    std::string output_path = "rm_traffic/data/bios_generated.jsonl";
    if (argc > 2) output_path = argv[2];

    std::random_device rd;
    std::mt19937 rng(rd());

    std::ofstream out(output_path);
    if (!out) {
        std::cerr << "Cannot open " << output_path << std::endl;
        return 1;
    }

    auto start = std::chrono::high_resolution_clock::now();

    for (int i = 0; i < count; i++) {
        std::string h = generate_headline(rng);
        std::string d = generate_description(rng);
        out << "{\"id\":\"cpp_" << i << "\",\"headline\":\"" << json_escape(h)
            << "\",\"description\":\"" << json_escape(d) << "\"}\n";
    }

    out.close();
    auto end = std::chrono::high_resolution_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    std::cout << "Generated " << count << " bios in " << ms << " ms" << std::endl;
    std::cout << "Rate: " << (count * 60000.0 / ms) << " bios/minute" << std::endl;
    std::cout << "Saved to: " << output_path << std::endl;
    return 0;
}
