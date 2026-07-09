"""
30 Bio Variant Modules — hypothesis-driven, tested copy strategies.

Each module is one variant. They rotate through positioning, tone, CTA,
local SEO, and client targeting. All are safe, professional, and funny-free.
"""

from typing import Dict, List

BioVariant = Dict[str, str]


def _bio(headline: str, description: str, hypothesis: str) -> BioVariant:
    return {"headline": headline, "description": description, "hypothesis": hypothesis}


BIO_VARIANTS: List[BioVariant] = [
    # Professional baseline
    _bio(
        "Deep Tissue & Sports Recovery — Manhattan",
        "I work with people who train hard, sit long hours, or carry stress in their shoulders, back, and hips. Sessions are pressure-forward, deliberate, and built around what your body needs that day. Clean private space in Manhattan. Message me with your focus areas and preferred time.",
        "Professional baseline tests broad appeal.",
    ),
    # Direct CTA
    _bio(
        "Strong Hands, Real Relief — Manhattan",
        "No fluff. No spa music required. Just focused deep tissue work on the muscle groups that actually hurt. I work with lifters, runners, desk workers, and travelers. Manhattan incall. Text or email to book a session.",
        "Direct CTA increases conversion intent.",
    ),
    # Local SEO heavy
    _bio(
        "Manhattan Deep Tissue Massage — Chelsea & Midtown",
        "Professional deep tissue and recovery massage in Manhattan. I see clients in Chelsea, Midtown, and surrounding areas. Focused on neck, shoulders, back, and hips. Strong, steady pressure. Same-day booking when available.",
        "Local SEO keywords improve Manhattan search relevance.",
    ),
    # Sports focus
    _bio(
        "Sports Recovery Massage — Manhattan",
        "Built for athletes and people who train. I target hips, hamstrings, glutes, shoulders, and back with firm pressure and slow, intentional work. Whether you lift, run, or fight, this is recovery for people who take their body seriously.",
        "Sports positioning attracts fitness-focused clients.",
    ),
    # Desk worker focus
    _bio(
        "Desk-Worker Relief — Manhattan Deep Tissue",
        "If your neck, shoulders, and lower back feel like concrete from hours at a desk, this is for you. I focus on the tension patterns that build from laptops, monitors, and stress. Pressure is adjusted to your tolerance. Manhattan.",
        "Desk-worker niche captures weekday traffic.",
    ),
    # Traveler focus
    _bio(
        "Travel Stiffness Relief — Manhattan",
        "Flights, luggage, and hotel beds leave the spine compressed and the neck locked. I work with travelers passing through Manhattan who need targeted relief before the next meeting or flight. Incall in Manhattan. Book when available.",
        "Traveler angle captures transient high-intent traffic.",
    ),
    # Premium positioning
    _bio(
        "Premium Bodywork — Manhattan, NYC",
        "Private, professional bodywork for clients who want quality over quantity. I combine deep tissue, pressure-point work, and full-body flow in a clean, comfortable Manhattan studio. Incall preferred. Established clients welcome.",
        "Premium positioning filters for higher-value bookings.",
    ),
    # Funny/personality
    _bio(
        "You Bring the Smile, I Bring the Wolf — Manhattan",
        "The name is Karpathian Wolf. The work is serious. I specialize in deep tissue and sports recovery for people who need real pressure and real relief. Manhattan incall. If you want a feather, go elsewhere. If you want to feel better, message me.",
        "Personality branding increases memorability.",
    ),
    # Recovery specialist
    _bio(
        "Recovery-Focused Bodywork in Manhattan",
        "Recovery is not the same as relaxation. I work on the muscle groups that take the load from training, travel, and long workdays. Slow, deliberate pressure. Clear communication. Manhattan. Message for availability.",
        "Recovery specialist framing increases trust with athletes.",
    ),
    # Concise
    _bio(
        "Deep Tissue Massage — Manhattan",
        "Focused, professional deep tissue work in Manhattan. Strong hands, clean space, clear communication. I work on the areas that hurt: shoulders, neck, back, hips. Message me to book.",
        "Concise copy reduces cognitive load.",
    ),
    # Last-minute availability
    _bio(
        "Same-Day Deep Tissue — Manhattan",
        "Need real bodywork today? I keep blocks open for same-day sessions in Manhattan when I am available. Strong pressure, clean space, no attitude. Text or email with your preferred time and focus areas.",
        "Last-minute availability converts urgent searches.",
    ),
    # Outcall emphasized
    _bio(
        "Manhattan Outcall Deep Tissue & Recovery",
        "I bring the session to your Manhattan location. Clean, professional, and focused on real relief. Best for clients who prefer privacy and convenience. Strong pressure, clear boundaries, respectful clients only.",
        "Outcall emphasis captures different client segment.",
    ),
    # Incall emphasized
    _bio(
        "Private Manhattan Studio — Deep Tissue",
        "My space is clean, private, and designed for focused work. No distractions. I offer deep tissue, sports recovery, and targeted relief in Manhattan. Incall only. Message to book.",
        "Incall emphasis reassures clients about environment.",
    ),
    # Pain-specific
    _bio(
        "Shoulder & Neck Tension Relief — Manhattan",
        "Specialized work on the upper back, shoulders, neck, and base of the skull. I address the tension that builds from stress, posture, and long hours. Slow pressure, clear communication. Manhattan.",
        "Pain-specific positioning improves relevance.",
    ),
    # Hip/glute focus
    _bio(
        "Hip & Glute Recovery — Manhattan",
        "Targeted work on hips, glutes, and lower back for people who sit, squat, or run. Deep, deliberate pressure on the muscle groups that connect the lower body. Manhattan incall. Message for availability.",
        "Lower-body focus targets lifters and runners.",
    ),
    # Stress reset
    _bio(
        "Stress Reset Bodywork — Manhattan",
        "Stress lives in the body. I work on the shoulders, neck, back, and hips to release the tension that accumulates from deadlines, screens, and city life. Manhattan incall. Calm space, strong hands, clear boundaries.",
        "Stress reset captures high-stress Manhattan professionals.",
    ),
    # Morning availability
    _bio(
        "Early Morning Deep Tissue — Manhattan",
        "Start the day with real bodywork. I offer early morning sessions in Manhattan for people who want to get ahead of tightness before work. Strong pressure, clean space, on-time. Message to schedule.",
        "Time-of-day positioning targets early schedulers.",
    ),
    # Evening availability
    _bio(
        "Evening Recovery Sessions — Manhattan",
        "After work, after the gym, after the city. Evening deep tissue sessions in Manhattan for people who need to decompress before bed. Strong pressure, clean space, respectful clients only. Message to book.",
        "Evening positioning targets after-work traffic.",
    ),
    # Weekend focus
    _bio(
        "Weekend Deep Tissue Recovery — Manhattan",
        "Use the weekend to recover properly. I offer longer, focused sessions on Saturday and Sunday in Manhattan. Deep tissue, sports recovery, and full-body work. Message for weekend availability.",
        "Weekend focus captures weekend search traffic.",
    ),
    # First-timer friendly
    _bio(
        "First-Timer Friendly Deep Tissue — Manhattan",
        "New to deep tissue? I explain the process, check in on pressure, and focus on the areas you want worked. No surprises. Clean, professional space in Manhattan. Message me with questions or to book.",
        "First-timer friendly reduces friction for new clients.",
    ),
    # Experienced clients
    _bio(
        "For Clients Who Know Good Pressure — Manhattan",
        "If you have tried light massages and left frustrated, this is for you. I deliver deep, consistent pressure on the areas that need it. No guesswork. Manhattan incall. Message with your focus areas.",
        "Experienced-client framing filters for pressure tolerance.",
    ),
    # Discretion
    _bio(
        "Discreet Professional Bodywork — Manhattan",
        "Private, discreet, and professional deep tissue work in Manhattan. I respect your privacy, your time, and your boundaries. Clean space, strong hands, clear communication. Message to arrange.",
        "Discretion framing increases trust with privacy-focused clients.",
    ),
    # Results-focused
    _bio(
        "Results-Focused Deep Tissue — Manhattan",
        "I measure a session by how you feel after, not by how it sounds. Targeted, pressure-forward work on the muscle groups that limit your movement. Manhattan incall. Message to book a session.",
        "Results-focused copy emphasizes practical outcomes.",
    ),
    # No-nonsense
    _bio(
        "No-Nonsense Deep Tissue — Manhattan",
        "Strong pressure. Clean space. Clear communication. I work on the areas that hurt until they feel better. No spa rituals, no upsells, no surprises. Manhattan incall. Message for availability.",
        "No-nonsense tone reduces perceived friction.",
    ),
    # Warm/friendly
    _bio(
        "Friendly, Focused Deep Tissue — Manhattan",
        "I take the work seriously, not myself. Sessions are professional, warm, and focused on your goals. Deep tissue, recovery, and targeted relief in a clean Manhattan space. Message to book.",
        "Warm tone increases approachability.",
    ),
    # Expert positioning
    _bio(
        "Manhattan Deep Tissue Specialist",
        "Deep tissue is not just hard pressure — it is knowing where to work, how deep, and for how long. I specialize in shoulders, back, hips, and sports recovery. Manhattan incall. Message with your needs.",
        "Specialist positioning increases perceived expertise.",
    ),
    # Client-centered
    _bio(
        "Your Session, Your Goals — Manhattan",
        "Every session starts with a quick check-in: what changed since last time, where is the tightness, and what pressure works for you. I build the session around your goals. Manhattan incall. Message to book.",
        "Client-centered copy increases trust.",
    ),
    # Manhattan specific neighborhoods
    _bio(
        "Hell's Kitchen & Chelsea Deep Tissue Massage",
        "Convenient location for clients in Hell's Kitchen, Chelsea, and Midtown Manhattan. Professional deep tissue and sports recovery in a clean private space. Strong pressure, clear communication. Message for availability.",
        "Neighborhood-specific local SEO improves micro-local relevance.",
    ),
    # Long-session focus
    _bio(
        "Long, Deep Sessions — Manhattan",
        "Some bodies need more than an hour. I offer longer sessions for clients who want full-body deep tissue work with time for shoulders, back, hips, and legs. Manhattan incall. Message for details.",
        "Long-session focus captures clients wanting thorough work.",
    ),
    # Quick-session focus
    _bio(
        "Focused 60-Minute Deep Tissue — Manhattan",
        "One hour, one focus area, real pressure. Ideal for clients who want targeted work on shoulders, neck, or back without committing to a longer session. Manhattan incall. Message to book.",
        "Quick-session focus lowers booking barrier.",
    ),
]


def get_variant(index: int) -> BioVariant:
    if 0 <= index < len(BIO_VARIANTS):
        v = BIO_VARIANTS[index]
        return {
            "variant_id": f"module_{index:02d}",
            "headline": v["headline"],
            "description": v["description"],
            "hypothesis": v["hypothesis"],
        }
    return None


def list_all() -> List[BioVariant]:
    return [get_variant(i) for i in range(len(BIO_VARIANTS))]


def count() -> int:
    return len(BIO_VARIANTS)
