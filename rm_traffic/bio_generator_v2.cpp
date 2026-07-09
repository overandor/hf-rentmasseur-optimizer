#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <random>
#include <chrono>
#include <unordered_map>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <iomanip>

std::vector<std::string> headline_templates = {
    "{adjective} {thing} — Manhattan",
    "{name} Delivers {thing} in Manhattan",
    "Manhattan {thing} for {person}",
    "{thing} Without the Fluff — Manhattan",
    "{body_part} {thing} in Manhattan",
    "{city} {thing} for {person}",
    "{adjective} {body_part} {thing} — Manhattan",
    "{person} Choose {thing} in Manhattan",
    "{name}: {thing} in Manhattan",
    "Real {thing} for {person} in {city}",
    "{thing} That Actually Works — Manhattan",
    "Manhattan's {adjective} {thing}",
    "{thing} for {person} — {city}",
    "{adjective} {thing} for {body_part} Relief",
    "{name} Does {thing} — {city}",
    "{thing} in Manhattan, NYC",
    "{body_part} Rescue in {city}",
    "{person} Recovery in Manhattan",
    "{thing} + {thing} in Manhattan",
    "{adjective} {thing} for {person}",
    "From {city} Stress to {thing}",
    "{thing}: The Manhattan Edition",
    "{name}'s {thing} — Manhattan",
    "{person} Get {thing} in Manhattan",
    "{thing} for {person} in NYC",
    "{body_part} and {body_part} {thing} — Manhattan",
    "{adjective} {thing} for {city} Clients",
    "{thing} Made Simple — Manhattan",
    "{person} Need {thing} — Manhattan",
    "{name} Presents: {thing} in {city}",
    "{thing} for {person} Who Train",
    "{thing} for {person} Who Sit",
    "{city} {thing} by {name}",
    "{adjective} {thing} for {body_part} Pain",
    "{thing} in {city} — {adjective}",
    "{person} Prefer {thing} in Manhattan",
    "Manhattan {thing} with {adjective} Pressure",
    "{thing} for {person} in {city}",
    "{body_part} {thing} for {person}",
    "{name}: {adjective} {thing} in Manhattan",
    "{thing} for {city}'s Busiest {person}",
    "{adjective} {thing} — {city}",
    "{thing} When You Need It — {city}",
    "{person} Trust {name} for {thing}",
    "{city} {thing} for {body_part} Recovery",
    "{adjective} {thing} in {city}",
    "{thing} for {person} in Manhattan",
    "{name}'s {adjective} {thing}",
    "{thing} in {city} for {person}",
    "{body_part} {thing} in {city}",
    "{adjective} {thing} for {city} {person}",
    "{thing} for {person} — {name}",
    "{city} {thing} with {name}",
    "{thing} That {person} Recommend",
    "{name}: {thing} for {city}",
    "{adjective} {thing} — {person} Edition",
    "{thing} for {body_part} and {body_part} in Manhattan",
    "{person} Book {thing} in {city}",
    "{name} Does {adjective} {thing}",
    "{city} {thing} for {person} Recovery",
    "{thing} in {city} — {adjective} {name}",
    "{adjective} {thing} for {person} in {city}",
    "{body_part} {thing} for {city} {person}",
    "{thing} in Manhattan — {adjective}",
    "{name}: {thing} for {person}",
    "{thing} for {city} {person}",
    "{adjective} {body_part} Work in {city}",
    "{thing} for {person} — {city}",
    "{city} {thing} by {name} — {adjective}",
    "{thing} for {person} with {body_part} Issues",
    "{name} {thing} in {city}",
    "{adjective} {thing} for {city} Professionals",
    "{thing} in {city} for {body_part} Relief",
    "{person} Get {adjective} {thing} in Manhattan",
    "{thing} — {city} {person}",
    "{name}: {city} {thing} Specialist",
    "{adjective} {thing} for {person} in {city}",
    "{body_part} {thing} by {name} in {city}",
    "{thing} for {person} Who Commute",
    "{city} {thing} for {body_part} and {body_part}",
    "{name} — {adjective} {thing} in {city}",
    "{thing} for {person} in {city} — {name}",
    "{adjective} {thing} for {city} {person}",
    "{person} {thing} in {city} with {name}",
    "{thing} for {body_part} Recovery in {city}",
    "{name} {thing} — {adjective}",
    "{city} {thing} for {person} Who Travel",
    "{thing} for {person} in {city} — {adjective}",
    "{adjective} {body_part} {thing} in {city}",
    "{name}: {thing} for {city} {person}",
    "{thing} in {city} — {person} Recommended",
    "{city} {thing} for {person} with {body_part} Tension",
    "{adjective} {thing} — {name} in {city}",
    "{thing} for {person} in {city} — {body_part} Focus",
    "{name} Does {thing} for {person} in {city}",
    "{city} {thing} — {adjective} {body_part}",
    "{thing} for {person} in {city} with {name}",
    "{adjective} {thing} for {city} {body_part} Recovery",
    "{person} in {city} Book {thing} with {name}",
};

std::vector<std::string> bio_templates = {
    "{hook}\n\n{specialty}\n\n{client}\n\n{style}\n\n{cta}",
    "{hook}\n\n{style}\n\n{specialty}\n\n{proof}\n\n{cta}",
    "{specialty}\n\n{client}\n\n{hook}\n\n{style}\n\n{cta}",
    "{hook}\n\n{proof}\n\n{specialty}\n\n{cta}",
    "{hook}\n\n{specialty}\n\n{style}\n\n{proof}\n\n{cta}",
    "{client}\n\n{hook}\n\n{specialty}\n\n{style}\n\n{cta}",
    "{hook}\n\n{style}\n\n{client}\n\n{specialty}\n\n{cta}",
    "{specialty}\n\n{style}\n\n{proof}\n\n{hook}\n\n{cta}",
    "{proof}\n\n{specialty}\n\n{client}\n\n{style}\n\n{cta}",
    "{hook}\n\n{client}\n\n{proof}\n\n{style}\n\n{cta}",
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
    "Your traps are not supposed to live next to your ears.",
    "If stress had a body, I would work on it.",
    "You can't hustle your way out of a locked hip.",
    "Your body keeps the score. I keep the pressure.",
    "Bad posture is the new smoking. I am the patch.",
    "There are two types of people: those who recover and those who complain.",
    "Your fascia is thirsty. I bring the water.",
    "A stiff body is a stiff mind. Let's loosen both.",
    "Your muscles are not dramatic. They are honest.",
    "Tension is just a knot waiting for a wolf.",
    "Your neck is not a coat hanger.",
    "Sitting is the enemy. Pressure is the weapon.",
    "Your lower back called. It said please.",
    "If your body had a check engine light, it would be on.",
    "I am the mechanic your body needs.",
    "Muscles tighten. Wolves loosen.",
    "Your shoulders are not earrings.",
    "The chair wins every day. I can reverse the score.",
    "You treat your car better than your spine.",
    "Your hips are not supposed to feel like concrete.",
    "If your body were a phone, it would be at 2% battery.",
    "I don't fix people. I fix tension.",
    "Your glutes forgot how to work. I remind them.",
    "Tightness is not a personality trait.",
    "Your spine is a stack. I straighten it.",
    "If your body were a building, it needs a renovation.",
    "I am not a magician. I am a pressure specialist.",
    "Your hamstrings are not guitar strings.",
    "A good session is cheaper than a bad back.",
    "Your posture is a story. Let me help rewrite it.",
};

std::vector<std::string> specialties = {
    "I specialize in deep tissue, sports recovery, and targeted relief for shoulders, neck, back, and hips.",
    "My focus is pressure-forward work: slow, deliberate, and built around the muscle groups that actually need it.",
    "I do deep tissue, recovery bodywork, and the kind of pressure that actually changes how you move.",
    "Sports recovery, deep tissue, and hip/glute work are my main zones.",
    "I work on the tension that builds from training, travel, and ten-hour desk days.",
    "My sessions combine deep tissue, targeted pressure-point work, and movement-focused recovery.",
    "I focus on the areas that hold stress: upper back, shoulders, neck, lower back, and hips.",
    "My approach is practical: find the restriction, apply pressure, restore range.",
    "I work with athletes, desk workers, travelers, and anyone whose body feels older than they are.",
    "My sessions are built around your goals, not a routine.",
    "I use deep tissue, myofascial work, and targeted pressure to address stubborn tightness.",
    "My specialty is turning knotted muscle into relaxed, functional tissue.",
    "I focus on shoulders, neck, lower back, hips, and glutes with strong, sustained pressure.",
    "My work is built for people who need real pressure, not a gentle rub.",
    "I combine deep tissue with active release techniques to improve mobility.",
    "My sessions are customized: some days need strength, some days need precision.",
    "I work on the muscle groups that carry your stress: traps, rhomboids, lats, QL, hip flexors.",
    "My approach is thorough: I don't skip the parts that actually hurt.",
    "I do the kind of work that makes you remember your body is connected.",
    "My pressure is deep, my pace is intentional, and my targets are specific.",
};

std::vector<std::string> clients = {
    "Best for lifters, runners, desk workers, and anyone who treats their body like a rental.",
    "Great if you sit all day, train hard, or fly too much.",
    "If your neck feels like a phone cord from 1997, you're my people.",
    "For clients who want real pressure, clear communication, and a clean space.",
    "You don't need to be an athlete. You need to be tight.",
    "Ideal for Manhattan professionals who carry stress in their shoulders and back.",
    "Perfect for gym regulars who need recovery between sessions.",
    "If you are a frequent traveler, your body needs a reset.",
    "For people who want a real session, not a spa day.",
    "If you have tried light massages and left frustrated, come here.",
    "Best for anyone who sits at a desk and wonders why their back hurts.",
    "Great for runners, cyclists, and lifters with tight hips and legs.",
    "If you wake up stiff and go to bed stiff, I can help.",
    "For people who hold their stress in their upper back and neck.",
    "Ideal if you need strong pressure and clear communication.",
    "Perfect for those who want targeted work, not a generic massage.",
    "If your body feels older than your age, you are the right client.",
    "Great for people recovering from intense training blocks.",
    "For clients who want to move better and hurt less.",
    "If you are tired of being told to relax when you actually need pressure, come here.",
};

std::vector<std::string> styles = {
    "My style is direct. I find the tension, apply pressure, and stay there until it releases.",
    "No spa music required. No fluffy rituals. Just focused work.",
    "I adjust pressure to your body, not a script.",
    "Strong hands, calm presence, zero attitude.",
    "I work with intention. Every minute has a target.",
    "My pressure is firm, my pace is slow, and my focus is specific.",
    "I communicate clearly and check in on pressure so the session stays productive.",
    "My sessions are clean, professional, and built around results.",
    "I don't guess. I listen to what you say and what your body shows.",
    "The work is precise, the space is calm, and the goal is relief.",
    "I work with pressure that matches your tolerance, not my ego.",
    "My sessions are slow and deliberate. I don't rush the parts that need time.",
    "I check in, but I also read your body. Quiet feedback is still feedback.",
    "My approach is therapeutic first, everything else second.",
    "I work on the tissue, not around it.",
    "My hands are steady, my pressure is consistent, and my focus is yours.",
    "I build trust through pressure that feels productive, not punishing.",
    "My sessions are professional, private, and pressure-forward.",
    "I move from area to area with purpose, not randomly.",
    "My style is efficient: I find the problem and stay on it until it changes.",
};

std::vector<std::string> proofs = {
    "Clients usually leave looser, taller, and less hostile toward their desk.",
    "The feedback I get most: 'I should have done this months ago.'",
    "One session won't fix ten years of bad posture, but it's a solid opening argument.",
    "I don't promise magic. I promise real pressure in the right places.",
    "Most clients notice improved range of motion after the first session.",
    "The most common thing I hear is: 'That was exactly what I needed.'",
    "My regulars book because they feel the difference in their training and daily life.",
    "I have worked with office workers, athletes, and performers across Manhattan.",
    "Clients often report sleeping better after a session.",
    "Many of my clients say their posture feels taller after the first visit.",
    "I have helped desk workers reduce their daily tension significantly.",
    "Athletes I work with report faster recovery between training sessions.",
    "My clients come back because they feel the results, not just the pampering.",
    "I have a track record of helping people with chronic shoulder tightness.",
    "Clients tell me they can finally turn their head without stiffness.",
    "My sessions are designed to produce measurable changes in how you feel.",
    "I have helped travelers reset their body after long flights.",
    "Clients appreciate that I focus on their goals, not a routine.",
    "My work has helped people return to training after tension-related setbacks.",
    "I measure success by how much better you move, not by how relaxed you feel.",
};

std::vector<std::string> ctas = {
    "Message me with your focus areas and we'll get you sorted.",
    "Manhattan incall. Text or email to book.",
    "Clean private space in Manhattan. DM me to set something up.",
    "If your body is ready, so am I. Message for availability.",
    "Book a session and let's make your muscles less dramatic.",
    "Text or email with your preferred time and focus areas.",
    "Reach out when you're ready to feel better.",
    "Contact me to schedule a session in Manhattan.",
    "Send me a message and tell me what needs work.",
    "Let's get your body back on your side. Book now.",
    "If you are ready to work on your body, I am ready to help.",
    "Message me with your problem areas and let's plan a session.",
    "Text me to check availability or ask questions.",
    "Email or DM me to set up your session in Manhattan.",
    "I respond quickly. Reach out and let's get started.",
    "Send a message and tell me what hurts. I will do the rest.",
    "Book your session and feel the difference.",
    "If you are in Manhattan and need real bodywork, contact me.",
    "Message me today. Your body will thank you tomorrow.",
    "Let's schedule a session that targets exactly what you need.",
};

std::vector<std::string> things = {
    "Sports Recovery", "Deep Tissue", "Bodywork", "Knot Removal", "Recovery",
    "Shoulder Rescue", "Hip Relief", "Back Therapy", "Desk Detox", "Stress Reset",
    "Muscle Recovery", "Pain Relief", "Tension Release", "Mobility Work", "Fascia Release",
    "Trigger Point Work", "Myofascial Release", "Active Recovery", "Body Maintenance", "Movement Therapy",
};

std::vector<std::string> adjectives = {
    "Serious", "Pressure-Forward", "Wolf-Approved", "No-Nonsense", "Focused",
    "Real", "Direct", "Professional", "High-Octane", "Tension-Finding",
    "Effective", "Results-Driven", "Targeted", "Intense", "Skilled",
    "Experienced", "Therapeutic", "Precision", "Deep", "Sustained",
};

std::vector<std::string> persons = {
    "Desk Workers", "Athletes", "Gym Rats", "Frequent Flyers", "Tired Humans",
    "Shoulders", "Hips", "Runners", "Lifters", "Stressed New Yorkers",
    "Professionals", "Travelers", "City People", "Busy Bodies", "Hard Workers",
    "Athletes", "Office Workers", "Commuters", "Shift Workers", "Remote Workers",
};

std::vector<std::string> body_parts = {
    "Shoulders", "Back", "Hips", "Neck", "Glutes",
    "Traps", "Hamstrings", "Quads", "Calves", "Forearms",
    "Lower Back", "Upper Back", "Mid Back", "Rhomboids", "Lats",
};

std::vector<std::string> cities = {
    "Manhattan", "Midtown", "Chelsea", "Hell's Kitchen", "NYC",
    "Upper West Side", "Tribeca", "SoHo", "West Village", "East Village",
    "Financial District", "Flatiron", "Gramercy", "Murray Hill", "NoMad",
};

std::vector<std::string> names = {
    "The Wolf", "Karpathian Wolf", "Wolf", "This Guy",
    "K",
    "Karpathian",
};

std::string replace_all(std::string str, const std::string& from, const std::string& to) {
    size_t start_pos = 0;
    while ((start_pos = str.find(from, start_pos)) != std::string::npos) {
        str.replace(start_pos, from.length(), to);
        start_pos += to.length();
    }
    return str;
}

std::string generate_headline(std::mt19937& rng) {
    std::uniform_int_distribution<int> dist(0, headline_templates.size() - 1);
    std::string h = headline_templates[dist(rng)];
    h = replace_all(h, "{thing}", things[std::uniform_int_distribution<int>(0, things.size()-1)(rng)]);
    h = replace_all(h, "{adjective}", adjectives[std::uniform_int_distribution<int>(0, adjectives.size()-1)(rng)]);
    h = replace_all(h, "{name}", names[std::uniform_int_distribution<int>(0, names.size()-1)(rng)]);
    h = replace_all(h, "{person}", persons[std::uniform_int_distribution<int>(0, persons.size()-1)(rng)]);
    h = replace_all(h, "{body_part}", body_parts[std::uniform_int_distribution<int>(0, body_parts.size()-1)(rng)]);
    h = replace_all(h, "{city}", cities[std::uniform_int_distribution<int>(0, cities.size()-1)(rng)]);
    return h;
}

std::string generate_description(std::mt19937& rng) {
    std::uniform_int_distribution<int> hook_dist(0, hooks.size() - 1);
    std::uniform_int_distribution<int> specialty_dist(0, specialties.size() - 1);
    std::uniform_int_distribution<int> client_dist(0, clients.size() - 1);
    std::uniform_int_distribution<int> style_dist(0, styles.size() - 1);
    std::uniform_int_distribution<int> proof_dist(0, proofs.size() - 1);
    std::uniform_int_distribution<int> cta_dist(0, ctas.size() - 1);
    std::uniform_int_distribution<int> template_dist(0, bio_templates.size() - 1);

    std::string hook = hooks[hook_dist(rng)];
    std::string specialty = specialties[specialty_dist(rng)];
    std::string client = clients[client_dist(rng)];
    std::string style = styles[style_dist(rng)];
    std::string proof = proofs[proof_dist(rng)];
    std::string cta = ctas[cta_dist(rng)];

    std::string t = bio_templates[template_dist(rng)];
    t = replace_all(t, "{hook}", hook);
    t = replace_all(t, "{specialty}", specialty);
    t = replace_all(t, "{client}", client);
    t = replace_all(t, "{style}", style);
    t = replace_all(t, "{proof}", proof);
    t = replace_all(t, "{cta}", cta);
    return t;
}

std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
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
